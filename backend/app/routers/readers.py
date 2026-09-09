import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.llrp import LLRPReaderError, fetch_reader_capabilities
from app.llrp_session import LLRPSessionError, disconnect_session, get_recent_tags, is_reading, start_reading, stop_reading
from app.reader_info import fetch_vendor_web_info

router = APIRouter(prefix="/api/readers", tags=["readers"])


def _get_reader_or_404(db: Session, label: str) -> models.Reader:
    reader = db.query(models.Reader).filter(models.Reader.label == label).first()
    if not reader:
        raise HTTPException(status_code=404, detail="Reader not found")
    return reader


def _default_label(ip_address: str) -> str:
    return ip_address.replace(".", "_")


def _serialize(reader: models.Reader) -> schemas.Reader:
    data = schemas.Reader.model_validate(reader).model_dump()
    data["reading"] = is_reading(reader.label)
    return schemas.Reader(**data)


@router.get("", response_model=list[schemas.Reader])
def list_readers(db: Session = Depends(get_db)):
    readers = db.query(models.Reader).order_by(models.Reader.label).all()
    return [_serialize(r) for r in readers]


@router.post("", response_model=schemas.Reader, status_code=201)
def create_reader(payload: schemas.ReaderCreate, db: Session = Depends(get_db)):
    ip_address = payload.ip_address.strip()
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise HTTPException(status_code=400, detail=f'"{ip_address}" is not a valid IP address')

    label = (payload.label or "").strip() or _default_label(ip_address)
    reader = models.Reader(ip_address=ip_address, label=label)
    db.add(reader)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'A reader labeled "{label}" already exists')
    db.refresh(reader)
    return _serialize(reader)


@router.get("/{label}", response_model=schemas.Reader)
def get_reader(label: str, db: Session = Depends(get_db)):
    return _serialize(_get_reader_or_404(db, label))


@router.post("/{label}/connect", response_model=schemas.Reader)
def connect_reader(label: str, db: Session = Depends(get_db)):
    """Opens a real LLRP session against the reader and issues
    GET_READER_CAPABILITIES (manufacturer, model, antenna port count) and
    GET_READER_CONFIG's AntennaProperties (which ports currently have an
    antenna actually connected), storing both. Synchronous one-shot
    connect/query/disconnect — no session is kept open afterward.

    LLRP itself only reports numeric vendor/model codes, so once the LLRP
    connect succeeds this also makes a best-effort attempt at the reader's
    own web admin page (Impinj or Zebra/Motorola) for human-readable
    manufacturer/model strings, overwriting the numeric ones on success.
    Any failure there (blocked port, reader doesn't expose it, unexpected
    page) is silently ignored — the numeric LLRP values are kept."""
    reader = _get_reader_or_404(db, label)
    try:
        caps = fetch_reader_capabilities(reader.ip_address)
    except LLRPReaderError as e:
        reader.status = models.ReaderStatus.DISCONNECTED.value
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))

    manufacturer, product = caps.manufacturer, caps.product
    web_info = fetch_vendor_web_info(reader.ip_address, caps.manufacturer)
    if web_info:
        manufacturer, product = web_info

    reader.status = models.ReaderStatus.CONNECTED.value
    reader.manufacturer = manufacturer
    reader.product = product
    reader.num_antennas = caps.num_antennas
    reader.connected_antennas = caps.connected_antennas
    db.commit()
    db.refresh(reader)
    return _serialize(reader)


@router.post("/{label}/disconnect", response_model=schemas.Reader)
def disconnect_reader(label: str, db: Session = Depends(get_db)):
    """Fully releases the reader: stops any active tag-streaming session
    (see .../stop) and closes its connection, then marks it disconnected."""
    reader = _get_reader_or_404(db, label)
    disconnect_session(reader.label)
    reader.status = models.ReaderStatus.DISCONNECTED.value
    db.commit()
    db.refresh(reader)
    return _serialize(reader)


@router.post("/{label}/start", response_model=schemas.Reader)
def start_reader(label: str, db: Session = Depends(get_db)):
    """Starts continuously reading tags: opens a persistent LLRP
    connection if one isn't already open, adds and enables a
    run-until-stopped inventory ROSpec, and starts a background listener
    thread that appends each tag read to an in-memory buffer (see
    .../tags). No-op if already reading."""
    reader = _get_reader_or_404(db, label)
    try:
        start_reading(reader.label, reader.ip_address)
    except LLRPSessionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    reader.status = models.ReaderStatus.CONNECTED.value
    db.commit()
    db.refresh(reader)
    return _serialize(reader)


@router.post("/{label}/stop", response_model=schemas.Reader)
def stop_reader(label: str, db: Session = Depends(get_db)):
    """Stops the tag-streaming ROSpec and listener thread. The underlying
    connection is left open (so a later .../start is fast) — use
    .../disconnect to fully release it. No-op if not currently reading."""
    reader = _get_reader_or_404(db, label)
    stop_reading(reader.label)
    db.refresh(reader)
    return _serialize(reader)


@router.get("/{label}/tags", response_model=schemas.ReaderTagsResponse)
def list_reader_tags(label: str, db: Session = Depends(get_db)):
    reader = _get_reader_or_404(db, label)
    return schemas.ReaderTagsResponse(reading=is_reading(reader.label), tags=get_recent_tags(reader.label))
