"""Persistent LLRP tag-streaming sessions, one per reader, kept alive in
this process's memory across requests — adapted from an operator-supplied
TagInventory class. Unlike llrp.py's fetch_reader_capabilities() (a single
request/response transaction that opens and closes its own connection),
starting a reader here opens a connection and leaves it open, with a
background thread continuously receiving RO_ACCESS_REPORT messages, until
explicitly stopped or disconnected.

Only meaningful with a single backend process (this app runs uvicorn
without --workers, so a module-level registry is safe — see
docker-entrypoint.sh). A multi-worker deployment would need to move this
state out of process memory.
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone

from pyllrp.LLRPConnector import LLRPConnector
from pyllrp.pyllrp import (
    ADD_ROSPEC_Message,
    AirProtocols,
    AISpec_Parameter,
    AISpecStopTrigger_Parameter,
    AISpecStopTriggerType,
    DELETE_ROSPEC_Message,
    DISABLE_ROSPEC_Message,
    ENABLE_ROSPEC_Message,
    HexFormatToStr,
    InventoryParameterSpec_Parameter,
    RO_ACCESS_REPORT_Message,
    ROBoundarySpec_Parameter,
    ROReportSpec_Parameter,
    ROReportTriggerType,
    ROSpec_Parameter,
    ROSpecState,
    ROSpecStartTrigger_Parameter,
    ROSpecStartTriggerType,
    ROSpecStopTrigger_Parameter,
    ROSpecStopTriggerType,
    TagReportContentSelector_Parameter,
)

from app.tag_stream import record_tag_read

log = logging.getLogger(__name__)

ROSPEC_ID = 123  # Arbitrary but fixed — only one ROSpec is ever active per session.
INVENTORY_PARAMETER_SPEC_ID = 1234
MAX_TAG_BUFFER = 5000  # Most recent reads kept in memory per reader, for the UI to poll.


class LLRPSessionError(Exception):
    """Raised for any failure starting/maintaining a tag-streaming session.
    The message is meant to be shown directly to the operator."""


class ReaderSession:
    """One persistent LLRP connection + background listener for one reader.
    start()/stop() toggle the continuous-inventory ROSpec and the listener
    thread; the underlying connection is left open across stop()s (so a
    later start() is fast) and only closed by disconnect()."""

    def __init__(self, ip_address: str, label: str = "", reader_id: str = ""):
        self.ip_address = ip_address
        self.label = label
        self.reader_id = reader_id  # the reader's own serial number, if known
        self.connector = None
        self.reading = False
        self.lock = threading.Lock()
        self.tags = deque(maxlen=MAX_TAG_BUFFER)

    def _handle_report(self, connector, report):
        """Runs on the background listener thread, not the request thread."""
        for tag in report.getTagData():
            epc = tag.get("EPC")
            if epc is None:
                continue
            tag_id = HexFormatToStr(epc)
            # Preserved from the operator-supplied source: only tags whose
            # hex-formatted EPC is all decimal digits are kept (their tags
            # are provisioned so a valid read is always digit-only).
            if not tag_id.isdigit():
                continue

            timestamp_us = tag.get("Timestamp")
            read_time = None
            if timestamp_us is not None:
                try:
                    # tagTimeToComputerTime returns a naive datetime (via
                    # datetime.utcfromtimestamp) that represents UTC without
                    # saying so — attach tzinfo explicitly so isoformat()
                    # produces an unambiguous offset. Without this, a
                    # timezone-less ISO string gets parsed as *local* time by
                    # JS's `new Date(...)`, silently shifting it by whatever
                    # the browser's UTC offset is.
                    read_time = self.connector.tagTimeToComputerTime(timestamp_us).replace(tzinfo=timezone.utc)
                except Exception:
                    read_time = datetime.now(timezone.utc)

            antenna_id = tag.get("AntennaID")
            peak_rssi = tag.get("PeakRSSI")
            time_iso = read_time.isoformat() if read_time else None

            self.tags.append(
                {
                    "tag": tag_id,
                    "antenna_id": antenna_id,
                    "peak_rssi": peak_rssi,
                    "time": time_iso,
                }
            )

            record_tag_read(
                antenna=antenna_id,
                rssi=peak_rssi,
                timestamp=read_time.timestamp() if read_time else None,
                tag=tag_id,
                time=time_iso,
                label=self.label,
                reader_id=self.reader_id,
            )

    def _build_rospec(self, antennas=None):
        antennas = antennas if antennas is not None else [0]  # 0 = all antennas.
        return ADD_ROSPEC_Message(
            Parameters=[
                ROSpec_Parameter(
                    ROSpecID=ROSPEC_ID,
                    CurrentState=ROSpecState.Disabled,
                    Parameters=[
                        ROBoundarySpec_Parameter(
                            Parameters=[
                                ROSpecStartTrigger_Parameter(ROSpecStartTriggerType=ROSpecStartTriggerType.Immediate),
                                ROSpecStopTrigger_Parameter(ROSpecStopTriggerType=ROSpecStopTriggerType.Null),
                            ]
                        ),
                        AISpec_Parameter(
                            AntennaIDs=antennas,
                            Parameters=[
                                AISpecStopTrigger_Parameter(AISpecStopTriggerType=AISpecStopTriggerType.Null),
                                InventoryParameterSpec_Parameter(
                                    InventoryParameterSpecID=INVENTORY_PARAMETER_SPEC_ID,
                                    ProtocolID=AirProtocols.EPCGlobalClass1Gen2,
                                ),
                            ],
                        ),
                        ROReportSpec_Parameter(
                            ROReportTrigger=ROReportTriggerType.Upon_N_Tags_Or_End_Of_ROSpec,
                            N=1,
                            Parameters=[
                                TagReportContentSelector_Parameter(
                                    EnableAntennaID=True,
                                    EnableFirstSeenTimestamp=True,
                                    EnablePeakRSSI=True,
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )

    def start(self, antennas=None):
        with self.lock:
            if self.reading:
                return

            if self.connector is None:
                connector = LLRPConnector()
                try:
                    connector.connect(self.ip_address)
                except (OSError, ValueError, RuntimeError) as e:
                    raise LLRPSessionError(f"Could not connect to reader at {self.ip_address}: {e}") from e
                self.connector = connector

            try:
                # Best-effort cleanup of any stale ROSpec left over from a
                # previous session (e.g. this backend restarted while a
                # reader was still enabled) — failures here are expected
                # and ignored, matching the source this was adapted from.
                self.connector.transact(DISABLE_ROSPEC_Message(ROSpecID=0))
                self.connector.transact(DELETE_ROSPEC_Message(ROSpecID=ROSPEC_ID))

                self.connector.removeAllHandlers()
                self.connector.addHandler(RO_ACCESS_REPORT_Message, self._handle_report)

                response = self.connector.transact(self._build_rospec(antennas))
                if not response.success():
                    raise LLRPSessionError(f"Failed to add ROSpec on {self.ip_address}: {response}")

                response = self.connector.transact(ENABLE_ROSPEC_Message(ROSpecID=ROSPEC_ID))
                if not response.success():
                    raise LLRPSessionError(f"Failed to enable ROSpec on {self.ip_address}: {response}")

                self.connector.startListener()
                self.reading = True
            except LLRPSessionError:
                self._teardown_connection()
                raise
            except (OSError, ValueError, RuntimeError) as e:
                self._teardown_connection()
                raise LLRPSessionError(f"Failed to start reading on {self.ip_address}: {e}") from e

    def stop(self):
        with self.lock:
            if not self.reading:
                return
            try:
                self.connector.stopListener()
                response = self.connector.transact(DISABLE_ROSPEC_Message(ROSpecID=ROSPEC_ID))
                if not response.success():
                    log.warning("Failed to disable ROSpec on %s: %s", self.ip_address, response)
                self.connector.transact(DELETE_ROSPEC_Message(ROSpecID=ROSPEC_ID))
                self.connector.removeAllHandlers()
            finally:
                self.reading = False

    def disconnect(self):
        with self.lock:
            if self.reading:
                # Inline stop (not self.stop(), which would deadlock re-acquiring self.lock).
                try:
                    self.connector.stopListener()
                    self.connector.transact(DISABLE_ROSPEC_Message(ROSpecID=ROSPEC_ID))
                    self.connector.transact(DELETE_ROSPEC_Message(ROSpecID=ROSPEC_ID))
                    self.connector.removeAllHandlers()
                except Exception as e:
                    log.warning("Error stopping reader %s during disconnect: %s", self.ip_address, e)
                self.reading = False
            self._teardown_connection()

    def _teardown_connection(self):
        if self.connector is not None:
            try:
                self.connector.disconnect()
            except Exception as e:
                log.warning("Error disconnecting reader %s: %s", self.ip_address, e)
            self.connector = None


# --- Registry: one ReaderSession per reader label, for the lifetime of this process. ---

_sessions: dict[str, ReaderSession] = {}
_registry_lock = threading.Lock()


def _get_or_create_session(label: str, ip_address: str, reader_id: str = "") -> ReaderSession:
    with _registry_lock:
        session = _sessions.get(label)
        if session is None or session.ip_address != ip_address:
            session = ReaderSession(ip_address, label=label, reader_id=reader_id)
            _sessions[label] = session
        else:
            # Refresh in case the reader's known serial number changed since
            # this session was first created (e.g. connected for the first
            # time after reading had already been started once).
            session.label = label
            session.reader_id = reader_id
        return session


def start_reading(label: str, ip_address: str, reader_id: str = "") -> None:
    _get_or_create_session(label, ip_address, reader_id).start()


def stop_reading(label: str) -> None:
    session = _sessions.get(label)
    if session:
        session.stop()


def disconnect_session(label: str) -> None:
    """Best-effort full teardown, called when the operator hits the plain
    Disconnect button — stops reading first if needed."""
    session = _sessions.get(label)
    if session:
        session.disconnect()


def is_reading(label: str) -> bool:
    session = _sessions.get(label)
    return bool(session and session.reading)


def get_recent_tags(label: str, clear: bool = False) -> list[dict]:
    session = _sessions.get(label)
    if not session:
        return []
    tags = list(session.tags)
    if clear:
        session.tags.clear()
    return tags
