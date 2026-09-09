"""HTTP-based vendor info lookup for readers whose IP also serves their own
web admin UI. Unlike LLRP's GET_READER_CAPABILITIES (see llrp.py), which only
reports numeric vendor/model codes, these scrape the reader's own web page
for actual human-readable manufacturer/model strings.

Used as a best-effort enrichment step after a successful LLRP connect: on
any failure here (network error, unexpected page contents), the caller
keeps the numeric codes LLRP already gave it. A single, short-timeout
attempt is made — no retries — since this runs synchronously inside the
connect request and a fast fallback to the already-known LLRP values beats
blocking the operator's "Connect" click.
"""

import logging

import requests

log = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 5


def _find_value(buffer: str, key: str) -> str:
    """Zebra/Motorola's about.psp page: pulls the value out of the first
    `value="..."` attribute following an occurrence of `key`."""
    pos_key = buffer.find(key)
    if pos_key == -1:
        return ""
    pos_val = buffer.find("value=", pos_key) + 7
    pos_val_end = pos_val
    while pos_val_end < len(buffer) and buffer[pos_val_end] != '"':
        pos_val_end += 1
    return buffer[pos_val:pos_val_end]


def _find_value_impinj(buffer: str, key: str) -> str:
    """Impinj's cgi-bin/index.cgi page: an HTML table where the value lives
    in the cell after the label cell — pulls the text out of the second
    `<td>` following an occurrence of `key`."""
    pos_key = buffer.find(key)
    if pos_key == -1:
        return ""
    pos_val = buffer.find("</td>", pos_key)
    pos_val = buffer.find("</td>", pos_val + 5)
    pos_val = buffer.rfind(">", pos_key + 5, pos_val) + 1
    pos_val_end = pos_val
    while pos_val_end < len(buffer) and buffer[pos_val_end] != "<":
        pos_val_end += 1
    return buffer[pos_val:pos_val_end]


def fetch_moto_info(ip_address: str) -> dict:
    """Zebra/Motorola readers expose this on their built-in web server."""
    r = requests.get(f"http://{ip_address}/help/about.psp", timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    body = r.text
    return {
        "mfr": _find_value(body, "info.manufacturer"),
        "make": _find_value(body, "info.make"),
        "model": _find_value(body, "info.model"),
        "sn": _find_value(body, "info.unit_number"),
    }


def fetch_impinj_info(ip_address: str) -> dict:
    """Impinj readers expose this on their built-in web server, behind the
    factory-default basic-auth credentials (root/impinj)."""
    r = requests.get(f"http://root:impinj@{ip_address}/cgi-bin/index.cgi", timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    body = r.text
    return {
        "mfr": "Impinj",
        "model": _find_value_impinj(body, "Model Name"),
        "sn": _find_value_impinj(body, "Serial Number"),
    }


def fetch_vendor_web_info(ip_address: str, llrp_manufacturer: str) -> tuple[str, str] | None:
    """Best-effort (manufacturer, product) enrichment from the reader's own
    web admin page. Which vendor's page to try is picked from the
    manufacturer LLRP already resolved — 'Impinj' tries the Impinj page,
    anything else tries the Zebra/Motorola page (the only other vendor this
    supports). Returns None on any failure or empty result; callers should
    keep the LLRP numeric values in that case."""
    try:
        info = fetch_impinj_info(ip_address) if llrp_manufacturer == "Impinj" else fetch_moto_info(ip_address)
    except requests.exceptions.RequestException as e:
        log.warning("Could not fetch vendor web info from %s: %s", ip_address, e)
        return None

    product = info.get("model") or ""
    if not product:
        return None
    manufacturer = info.get("mfr") or llrp_manufacturer
    return manufacturer, product
