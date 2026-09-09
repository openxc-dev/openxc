"""Thin synchronous wrapper around pyllrp for the two operations needed so
far: GET_READER_CAPABILITIES (manufacturer, model, antenna port count) and
GET_READER_CONFIG's AntennaProperties (which of those ports currently has
an antenna actually plugged in), issued when an operator hits "Connect".
This opens a real LLRP session (TCP connect + the READER_EVENT_NOTIFICATION
handshake), transacts both messages, and closes the session again — there's
no persistent session kept open, and no ROSpec/tag-report streaming yet;
turning antenna reads into finish times is still follow-up work.
"""

from dataclasses import dataclass
from typing import Optional

from pyllrp.LLRPConnector import LLRPConnector
from pyllrp.pyllrp import (
    AntennaProperties_Parameter,
    GET_READER_CAPABILITIES_Message,
    GET_READER_CONFIG_Message,
    GeneralDeviceCapabilities_Parameter,
    GetReaderCapabilitiesRequestedData,
    GetReaderConfigRequestedData,
    LLRPStatus_Parameter,
    getVendorName,
)

LLRP_PORT = 5084
CONNECT_TIMEOUT_SECONDS = 5.0


class LLRPReaderError(Exception):
    """Any failure talking to a reader over LLRP — connection refused or
    timed out, a broken/short session, or a well-formed error response.
    The message is meant to be shown directly to the operator."""


@dataclass
class ReaderCapabilities:
    manufacturer: str
    product: str
    num_antennas: int
    # Antenna IDs (1-based) the reader reports as currently having an
    # antenna plugged in — distinct from num_antennas, which is just the
    # reader's total port count regardless of what's connected. None means
    # this reader didn't answer the AntennaProperties query (not fatal —
    # capabilities themselves already succeeded), so per-antenna status is
    # simply unknown, not "nothing connected".
    connected_antennas: Optional[list[int]] = None


def _parse_capabilities_response(response) -> ReaderCapabilities:
    """Pulled out of fetch_reader_capabilities() so it can be unit-tested
    against a response object built directly with pyllrp constructors,
    without needing a real socket round trip."""
    if not response.success():
        status = response.getFirstParameterByClass(LLRPStatus_Parameter)
        detail = status.ErrorDescription if status else "unknown error"
        raise LLRPReaderError(f"GET_READER_CAPABILITIES failed: {detail}")

    caps = response.getFirstParameterByClass(GeneralDeviceCapabilities_Parameter)
    if not caps:
        raise LLRPReaderError("Reader did not report GeneralDeviceCapabilities")

    return ReaderCapabilities(
        # DeviceManufacturerName is an IANA Private Enterprise Number, not a
        # string — getVendorName() resolves known ones (e.g. Impinj) to a
        # name and falls back to the raw numeric code otherwise. ModelName is
        # likewise a vendor-assigned numeric code with no generic name table,
        # so it's kept as-is; a human-readable product name would need a
        # per-vendor lookup this library doesn't provide.
        manufacturer=getVendorName(caps.DeviceManufacturerName),
        product=str(caps.ModelName),
        num_antennas=caps.MaxNumberOfAntennaSupported,
    )


def _parse_antenna_properties(response) -> Optional[list[int]]:
    """Same split-out-for-testing rationale as _parse_capabilities_response.
    Failure here doesn't raise — it's a secondary, non-essential query."""
    if not response.success():
        return None
    return sorted(
        p.AntennaID
        for p in response.getAllParametersByClass(AntennaProperties_Parameter)
        if p.AntennaConnected
    )


def fetch_reader_capabilities(ip_address: str) -> ReaderCapabilities:
    conn = LLRPConnector()
    conn.TimeoutSecs = CONNECT_TIMEOUT_SECONDS
    try:
        conn.connect(ip_address, LLRP_PORT)
        cap_response = conn.transact(
            GET_READER_CAPABILITIES_Message(RequestedData=GetReaderCapabilitiesRequestedData.All)
        )
        config_response = conn.transact(
            GET_READER_CONFIG_Message(
                AntennaID=0,  # 0 = all antennas, per the LLRP spec's convention
                RequestedData=GetReaderConfigRequestedData.AntennaProperties,
            )
        )
    except (OSError, ValueError, RuntimeError) as e:
        # OSError covers connection-refused/timed-out/unreachable (including
        # LLRPConnector.connect()'s own EnvironmentError, an OSError alias,
        # for a well-formed but non-Success ConnectionAttemptEvent — e.g. the
        # reader already has another client connected). ValueError/RuntimeError
        # cover a malformed or truncated handshake.
        raise LLRPReaderError(f"Could not reach reader at {ip_address}:{LLRP_PORT} ({e})") from e
    finally:
        conn.disconnect()

    caps = _parse_capabilities_response(cap_response)
    caps.connected_antennas = _parse_antenna_properties(config_response)
    return caps
