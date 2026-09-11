// A deliberately tiny HTTP server exposing Valkey/Redis pub/sub channels as
// Server-Sent Events: GET /events/<channel> subscribes and streams every
// message published to <channel> as it arrives, for as long as the client
// stays connected.
//
// It knows nothing about tag reads, readers, or any other OpenXC-specific
// concept; <channel> is whatever the client asks for.
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	valkeyHost = getEnv("VALKEY_HOST", "valkey")
	valkeyPort = getEnv("VALKEY_PORT", "6379")
	httpPort   = getEnv("PORT", "8001")

	// How often to send an SSE comment line when nothing's been published,
	// so intermediate proxies (nginx) and the browser don't treat an
	// idle-but-alive connection as dead. Comfortably under nginx's default
	// 60s proxy_read_timeout even before accounting for the longer timeout
	// set in nginx/default.conf.
	keepaliveSeconds = getEnvFloat("KEEPALIVE_SECONDS", 15)
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

func healthzHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, "OK")
}

func eventsHandler(rdb *redis.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
		if len(parts) != 2 || parts[0] != "events" || parts[1] == "" {
			http.NotFound(w, r)
			return
		}
		channel := parts[1]

		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming unsupported", http.StatusInternalServerError)
			return
		}

		ctx := r.Context()
		sub := rdb.Subscribe(ctx, channel)
		defer sub.Close()

		if _, err := sub.Receive(ctx); err != nil {
			log.Printf("could not subscribe to %q for %s: %v", channel, r.RemoteAddr, err)
			http.Error(w, "Bad Gateway", http.StatusBadGateway)
			return
		}

		log.Printf("subscribed %s to channel %q", r.RemoteAddr, channel)
		defer log.Printf("unsubscribed %s from channel %q", r.RemoteAddr, channel)

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("X-Accel-Buffering", "no") // belt-and-suspenders alongside nginx's own proxy_buffering off
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, ": connected\n\n")
		flusher.Flush()

		ch := sub.Channel()
		keepalive := time.NewTicker(time.Duration(keepaliveSeconds * float64(time.Second)))
		defer keepalive.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case msg, ok := <-ch:
				if !ok {
					return
				}
				if _, err := fmt.Fprint(w, sseEncode(msg.Payload)); err != nil {
					return
				}
				flusher.Flush()
			case <-keepalive.C:
				if _, err := fmt.Fprint(w, ": keep-alive\n\n"); err != nil {
					return
				}
				flusher.Flush()
			}
		}
	}
}

// sseEncode formats a message as an SSE "data:" frame. SSE requires each
// line of a multi-line payload to get its own "data:" prefix; our payloads
// are single-line JSON, but this stays correct if that ever changes.
func sseEncode(data string) string {
	data = strings.ReplaceAll(data, "\r\n", "\n")
	lines := strings.Split(data, "\n")
	var b strings.Builder
	for _, line := range lines {
		b.WriteString("data: ")
		b.WriteString(line)
		b.WriteString("\n")
	}
	b.WriteString("\n")
	return b.String()
}

func main() {
	log.SetFlags(log.LstdFlags)

	rdb := redis.NewClient(&redis.Options{
		Addr: valkeyHost + ":" + valkeyPort,
	})
	defer rdb.Close()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthzHandler)
	mux.HandleFunc("/events/healthz", healthzHandler)
	mux.HandleFunc("/events/", eventsHandler(rdb))

	srv := &http.Server{
		Addr:    ":" + httpPort,
		Handler: mux,
		// No global read/write timeout: SSE connections are meant to stay
		// open indefinitely. ReadHeaderTimeout still guards against slow
		// clients that never finish sending headers.
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("SSE events server listening on :%s, Valkey at %s:%s", httpPort, valkeyHost, valkeyPort)
	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
