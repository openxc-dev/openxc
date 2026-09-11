// Watches a host-written trigger file for starting-gun events and posts
// each one to the OpenXC starts API. If MEET_ID is set, posts to
// POST /api/meets/{meet_id}/starts; otherwise posts to POST /api/starts,
// which resolves to whichever meet is currently marked "active" in the
// dashboard — the simpler option day-to-day, since it needs no per-meet
// reconfiguration here.
//
// Each start is also mirrored into Valkey: XADDed to the shared `livestream`
// stream (the same one backend/app/tag_stream.py writes tag reads to, so a
// consumer scanning that stream sees both kinds of event, told apart by
// `event_type`) and PUBLISHed to the `start` pub/sub channel, for live
// subscribers (see events/server.go's SSE bridge, e.g. GET /events/start).
// Both are best-effort, same as the tag-read side — a Valkey outage never
// blocks or fails the actual start, which is the POST above.
//
// The trigger file (TRIGGER_FILE, default /var/run/trigger_events) is written
// by host-side/hardware code whenever the starting gun fires: each firing
// *appends* an 8-byte binary integer to the file — a CLOCK_MONOTONIC reading,
// in nanoseconds by default, taken at the moment of the trigger. So the file
// only ever grows, one 8-byte record per event, oldest first. See README.md
// in this directory for the full format assumptions (byte order, unit) and
// why a monotonic reading only converts correctly to wall-clock time when
// this container shares a kernel with whatever wrote the file (true on a
// native Linux host or a Raspberry Pi; NOT true through Docker Desktop's VM).
//
// At startup, this process notes the file's current size and reports nothing
// already present — only records appended *after* it started watching. From
// then on, every time the file grows by 8 bytes it reads and reports that
// new trailing record (not the file's first record, which is what a naive
// "always read the first 8 bytes" implementation would keep re-reading).
//
// Watched two ways at once, per the operator's request for redundancy:
//   - inotify, for near-instant detection.
//   - a periodic poll, in case inotify doesn't fire (bind-mounted host files
//     don't always propagate filesystem events reliably into a container).
//
// Both feed into the same offset-tracking check, so whichever notices growth
// first is the one that reads and posts the new record(s); the other is a
// no-op until the file grows again.
package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
	"unsafe"

	"github.com/redis/go-redis/v9"
	"golang.org/x/sys/unix"
)

// --- Configuration -----------------------------------------------------

var (
	triggerFile = getEnv("TRIGGER_FILE", "/var/run/trigger_events")
	apiBaseURL  = strings.TrimRight(getEnv("API_BASE_URL", "http://backend:8000"), "/")
	meetID      = strings.TrimSpace(os.Getenv("MEET_ID"))
	label       = getEnv("LABEL", "Starting Gun")
	pollInterval = time.Duration(getEnvFloat("POLL_INTERVAL_SECONDS", 5) * float64(time.Second))

	valkeyHost         = getEnv("VALKEY_HOST", "valkey")
	valkeyPort         = getEnv("VALKEY_PORT", "6379")
	valkeyStreamKey    = "livestream"
	valkeyStartChannel = "start"

	// How the 8 bytes in the trigger file are interpreted. Both are
	// adjustable without touching code, in case the actual host writer
	// differs from the assumed "little-endian, nanoseconds" convention.
	valueByteOrder = getEnv("VALUE_BYTE_ORDER", "little") // "little" or "big"
	valueUnit      = getEnv("VALUE_UNIT", "ns")            // "ns", "us", "ms", or "s"
	unitToNs       = map[string]int64{"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}

	// Guards against posting nonsense if the file is empty/zeroed/
	// misconfigured: a resulting event time further than this from "now"
	// is dropped, not posted.
	maxReasonableDelaySeconds = getEnvFloat("MAX_REASONABLE_DELAY_SECONDS", 3600)

	// HTTP retry policy for the POST itself (transient backend hiccups).
	postRetries           = 3
	postRetryDelay        = 2 * time.Second
)

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return fallback
}

// --- Minimal inotify binding --------------------------------------------
//
// We watch the *containing directory*, not the trigger file itself, and
// filter events by filename. Watching the file directly binds the watch to
// its current inode; if the writer replaces the file via the standard
// atomic-write pattern (write a temp file, then rename() over the target —
// the safe way to avoid a reader seeing a torn/partial write), that inode is
// swapped out from under us and a file-level watch silently stops seeing
// anything. Watching the directory for CREATE/MOVED_TO/CLOSE_WRITE events
// naming our file catches both in-place writes and atomic replacements.

const watchMask = unix.IN_MODIFY | unix.IN_ATTRIB | unix.IN_CLOSE_WRITE | unix.IN_CREATE | unix.IN_MOVED_TO

type inotifyEvent struct {
	Name string
}

type Inotify struct {
	fd int
}

func newInotify() (*Inotify, error) {
	fd, err := unix.InotifyInit1(0)
	if err != nil {
		return nil, fmt.Errorf("inotify_init1 failed: %w", err)
	}
	return &Inotify{fd: fd}, nil
}

func (in *Inotify) watch(path string) error {
	_, err := unix.InotifyAddWatch(in.fd, path, watchMask)
	if err != nil {
		return fmt.Errorf("inotify_add_watch failed for %s: %w", path, err)
	}
	return nil
}

// readEvents blocks up to timeoutMs for events; returns a nil slice on
// timeout.
func (in *Inotify) readEvents(timeoutMs int) ([]inotifyEvent, error) {
	fds := []unix.PollFd{{Fd: int32(in.fd), Events: unix.POLLIN}}
	n, err := unix.Poll(fds, timeoutMs)
	if err != nil {
		if err == unix.EINTR {
			return nil, nil
		}
		return nil, err
	}
	if n == 0 {
		return nil, nil
	}
	buf := make([]byte, 64*1024)
	nread, err := unix.Read(in.fd, buf)
	if err != nil {
		return nil, err
	}
	return parseInotifyEvents(buf[:nread]), nil
}

func parseInotifyEvents(buf []byte) []inotifyEvent {
	const headerSize = unix.SizeofInotifyEvent
	var events []inotifyEvent
	off := 0
	for off+headerSize <= len(buf) {
		raw := (*unix.InotifyEvent)(unsafe.Pointer(&buf[off]))
		nameStart := off + headerSize
		nameEnd := nameStart + int(raw.Len)
		if nameEnd > len(buf) {
			break
		}
		name := ""
		if raw.Len > 0 {
			nameBytes := buf[nameStart:nameEnd]
			if idx := bytes.IndexByte(nameBytes, 0); idx >= 0 {
				name = string(nameBytes[:idx])
			} else {
				name = string(nameBytes)
			}
		}
		events = append(events, inotifyEvent{Name: name})
		off = nameEnd
	}
	return events
}

func (in *Inotify) close() error {
	return unix.Close(in.fd)
}

// --- Trigger file handling ------------------------------------------------

// statFile returns the file's size and whether it exists. A directory in
// place of the trigger file is reported via isDir.
func statFile(path string) (size int64, exists bool, isDir bool) {
	info, err := os.Stat(path)
	if err != nil {
		return 0, false, false
	}
	return info.Size(), true, info.IsDir()
}

// monotonicNsToWallclock converts a CLOCK_MONOTONIC nanosecond reading into
// a wall-clock time by diffing it against *this process's own* current
// monotonic and real-time clocks. CLOCK_MONOTONIC's zero point is arbitrary
// and not portable across machines/processes, so the raw value is never
// treated as an absolute time — only the elapsed delta is meaningful, which
// is valid as long as this container observes the same monotonic clock as
// whatever wrote the file (true on a native Linux host / Raspberry Pi; not
// true through Docker Desktop's VM — see README.md).
func monotonicNsToWallclock(triggerMonotonicNs int64) (time.Time, int64) {
	var monoTs, realTs unix.Timespec
	_ = unix.ClockGettime(unix.CLOCK_MONOTONIC, &monoTs)
	_ = unix.ClockGettime(unix.CLOCK_REALTIME, &realTs)
	nowMonotonicNs := int64(monoTs.Sec)*1_000_000_000 + int64(monoTs.Nsec)
	nowRealNs := int64(realTs.Sec)*1_000_000_000 + int64(realTs.Nsec)
	elapsedNs := nowMonotonicNs - triggerMonotonicNs
	eventRealNs := nowRealNs - elapsedNs
	return time.Unix(0, eventRealNs).UTC(), elapsedNs
}

func postStart(eventTime time.Time) {
	url := apiBaseURL + "/api/starts"
	if meetID != "" {
		url = apiBaseURL + "/api/meets/" + meetID + "/starts"
	}
	isoTime := formatISO(eventTime)
	payload, _ := json.Marshal(map[string]string{"label": label, "time": isoTime})

	client := &http.Client{Timeout: 10 * time.Second}
	for attempt := 1; attempt <= postRetries; attempt++ {
		req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(payload))
		if err != nil {
			log.Printf("could not build request to %s: %v", url, err)
			return
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			log.Printf("POST %s failed (attempt %d/%d): %v", url, attempt, postRetries, err)
			if attempt < postRetries {
				time.Sleep(postRetryDelay)
			}
			continue
		}

		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		if resp.StatusCode >= 400 {
			log.Printf("POST %s failed: HTTP %d %s", url, resp.StatusCode, string(body))
			return // a 4xx/5xx from the API won't be fixed by retrying the same body
		}
		log.Printf("Posted start %s -> HTTP %d", isoTime, resp.StatusCode)
		return
	}
	log.Printf("Giving up posting start %s after %d attempts", isoTime, postRetries)
}

// formatISO matches Python's datetime.isoformat() for a UTC-aware
// datetime, e.g. "2026-09-11T15:02:51.327377+00:00" — microsecond
// precision with an explicit numeric offset rather than Go's default "Z"
// suffix, for consistency with backend/app/llrp_session.py's timestamps.
func formatISO(t time.Time) string {
	return t.UTC().Format("2006-01-02T15:04:05.000000") + "+00:00"
}

var (
	valkeyClient     *redis.Client
	valkeyClientOnce sync.Once
)

func getValkeyClient() *redis.Client {
	valkeyClientOnce.Do(func() {
		valkeyClient = redis.NewClient(&redis.Options{Addr: valkeyHost + ":" + valkeyPort})
	})
	return valkeyClient
}

// recordStartEvent is a best-effort mirror of a start into Valkey,
// alongside the authoritative POST in postStart() above: XADD onto the
// shared `livestream` stream, and PUBLISH to the `start` channel for live
// subscribers. Failures here are logged and otherwise ignored — this is a
// supplementary broadcast, not the real delivery mechanism for a start.
func recordStartEvent(eventTime time.Time) {
	isoTime := formatISO(eventTime)
	fields := map[string]interface{}{
		"event_type": "start",
		"label":      label,
		"meet_id":    meetID,
		"time":       isoTime,
		"timestamp":  strconv.FormatFloat(float64(eventTime.UnixNano())/1e9, 'f', -1, 64),
	}

	ctx := context.Background()
	client := getValkeyClient()
	if err := client.XAdd(ctx, &redis.XAddArgs{Stream: valkeyStreamKey, Values: fields}).Err(); err != nil {
		log.Printf("Could not write start event to Valkey stream %q: %v", valkeyStreamKey, err)
	}
	payload, _ := json.Marshal(fields)
	if err := client.Publish(ctx, valkeyStartChannel, payload).Err(); err != nil {
		log.Printf("Could not publish start event to Valkey channel %q: %v", valkeyStartChannel, err)
	}
}

// --- Append-tracking change detection --------------------------------------

// TriggerWatcher tracks how much of the (append-only) trigger file has been
// consumed so far, as a byte offset shared between the inotify goroutine and
// the poll loop — whichever notices growth first reads and posts the new
// record(s); the other is a no-op until the file grows again. Starts at the
// file's current size, so restarting this process doesn't re-post records
// that were already there before it started watching.
type TriggerWatcher struct {
	path string
	mu   sync.Mutex
	offset int64
}

func newTriggerWatcher(path string) *TriggerWatcher {
	size, exists, _ := statFile(path)
	tw := &TriggerWatcher{path: path}
	if exists {
		tw.offset = size
	}
	if tw.offset > 0 {
		log.Printf(
			"%s already has %d bytes (%d prior record(s)) — starting from the end; "+
				"only records appended from now on will be reported.",
			path, tw.offset, tw.offset/8,
		)
	}
	return tw
}

func (tw *TriggerWatcher) check(source string) {
	tw.mu.Lock()
	size, exists, isDir := statFile(tw.path)
	if !exists {
		tw.mu.Unlock()
		return
	}
	if isDir {
		tw.mu.Unlock()
		log.Printf("%s is a directory, not a file — check TRIGGER_FILE.", tw.path)
		return
	}
	if size < tw.offset {
		log.Printf(
			"%s shrank from %d to %d bytes — it was likely recreated as a new file; "+
				"treating all %d byte(s) currently in it as unseen.",
			tw.path, tw.offset, size, size,
		)
		tw.offset = 0
	}
	count := (size - tw.offset) / 8
	if count == 0 {
		tw.mu.Unlock()
		return
	}

	f, err := os.Open(tw.path)
	if err != nil {
		tw.mu.Unlock()
		return
	}
	buf := make([]byte, count*8)
	n, err := f.ReadAt(buf, tw.offset)
	f.Close()
	if err != nil && err != io.EOF {
		tw.mu.Unlock()
		return
	}
	// Only consume whole 8-byte records — a short read means we raced an
	// in-progress append; the remainder is picked up next time the file
	// grows past a full record boundary.
	count = int64(n) / 8
	if count == 0 {
		tw.mu.Unlock()
		return
	}
	raw := buf[:count*8]
	tw.offset += count * 8
	tw.mu.Unlock()

	log.Printf("%s grew by %d record(s), detected via %s", tw.path, count, source)
	for i := int64(0); i < count; i++ {
		chunk := raw[i*8 : i*8+8]
		var rawValue uint64
		if valueByteOrder == "little" {
			rawValue = binary.LittleEndian.Uint64(chunk)
		} else {
			rawValue = binary.BigEndian.Uint64(chunk)
		}
		tw.report(int64(rawValue) * unitToNs[valueUnit])
	}
}

func (tw *TriggerWatcher) report(triggerMonotonicNs int64) {
	eventTime, elapsedNs := monotonicNsToWallclock(triggerMonotonicNs)
	elapsedSeconds := float64(elapsedNs) / 1e9
	if math.Abs(elapsedSeconds) > maxReasonableDelaySeconds {
		log.Printf(
			"Ignoring trigger record monotonic_ns=%d: computed event time %s is %.0fs from now, "+
				"past MAX_REASONABLE_DELAY_SECONDS=%.0f — likely a misread or misconfigured trigger "+
				"file, not a real event.",
			triggerMonotonicNs, formatISO(eventTime), elapsedSeconds, maxReasonableDelaySeconds,
		)
		return
	}
	postStart(eventTime)
	recordStartEvent(eventTime)
}

func inotifyLoop(watcher *TriggerWatcher, stop <-chan struct{}) {
	targetDir := filepath.Dir(watcher.path)
	if targetDir == "" {
		targetDir = "."
	}
	targetName := filepath.Base(watcher.path)

	for {
		select {
		case <-stop:
			return
		default:
		}

		in, err := newInotify()
		if err != nil {
			log.Printf("inotify error (%v); restarting watch in 5s", err)
			if sleepOrStop(5*time.Second, stop) {
				return
			}
			continue
		}
		if err := in.watch(targetDir); err != nil {
			in.close()
			log.Printf("%s does not exist yet or is unwatchable (%v); retrying inotify watch in 5s", targetDir, err)
			if sleepOrStop(5*time.Second, stop) {
				return
			}
			continue
		}
		log.Printf("inotify watching %s for changes to %s", targetDir, targetName)

	inner:
		for {
			select {
			case <-stop:
				in.close()
				return
			default:
			}
			events, err := in.readEvents(2000)
			if err != nil {
				log.Printf("inotify error (%v); restarting watch in 5s", err)
				break inner
			}
			for _, ev := range events {
				if ev.Name == targetName {
					watcher.check("inotify")
					break
				}
			}
		}
		in.close()
		if sleepOrStop(5*time.Second, stop) {
			return
		}
	}
}

func sleepOrStop(d time.Duration, stop <-chan struct{}) bool {
	select {
	case <-time.After(d):
		return false
	case <-stop:
		return true
	}
}

func pollLoop(watcher *TriggerWatcher, stop <-chan struct{}) {
	for {
		watcher.check("poll")
		if sleepOrStop(pollInterval, stop) {
			return
		}
	}
}

func main() {
	log.SetFlags(log.LstdFlags)

	target := "the active meet"
	if meetID != "" {
		target = "meet " + meetID
	}
	log.Printf(
		"Watching %s (unit=%s, byte_order=%s), posting to %s as label=%q for %s "+
			"(poll every %.0fs as an inotify fallback)",
		triggerFile, valueUnit, valueByteOrder, apiBaseURL, label, target, pollInterval.Seconds(),
	)
	if meetID == "" {
		log.Print(
			"MEET_ID is not set, so posts go to /api/starts (the active meet). " +
				"Mark a meet active in the dashboard before the gun fires, or set " +
				"MEET_ID to always post to one specific meet.",
		)
	}

	watcher := newTriggerWatcher(triggerFile)
	stop := make(chan struct{})

	go inotifyLoop(watcher, stop)
	pollLoop(watcher, stop)
}
