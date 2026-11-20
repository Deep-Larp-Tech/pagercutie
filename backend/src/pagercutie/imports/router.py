from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePath
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.sse import EventSourceResponse

from pagercutie.core.deps import SessionmakerDep, SettingsDep
from pagercutie.core.errors import DomainError, error_body
from pagercutie.core.schemas import json_error_responses
from pagercutie.imports import service
from pagercutie.imports.schemas import ImportCompleted, ImportEvent, ImportFailed, ImportFormat, ImportSummaryRead

log = structlog.get_logger("imports")

router = APIRouter(prefix="/imports", tags=["imports"])

_CONTENT_TYPES = {
    "application/json": ImportFormat.JSON,
    "text/csv": ImportFormat.CSV,
    "application/csv": ImportFormat.CSV,
}


@dataclass(frozen=True)
class Upload:
    content: bytes
    fmt: ImportFormat


def _detect_format(file: UploadFile) -> ImportFormat:
    suffix = PurePath(file.filename or "").suffix.lower().removeprefix(".")
    if suffix in ImportFormat:
        return ImportFormat(suffix)
    if file.content_type in _CONTENT_TYPES:
        return _CONTENT_TYPES[file.content_type]
    raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .json or .csv file")


async def read_upload(file: UploadFile, settings: SettingsDep) -> Upload:
    # A dependency, so these run before the stream starts and still answer with a real HTTP status.
    fmt = _detect_format(file)
    content = await file.read(settings.import_max_bytes + 1)
    if len(content) > settings.import_max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.import_max_bytes} bytes")
    return Upload(content, fmt)


@router.post("/larp-events", response_class=EventSourceResponse, responses=json_error_responses(400, 413, 415))
async def import_larp_events(
    upload: Annotated[Upload, Depends(read_upload)], sessionmaker: SessionmakerDep
) -> AsyncIterator[ImportEvent]:
    """Create LARPing events from a JSON or CSV file, creating missing persons and skills on the way.

    Streams progress events, then exactly one `completed` (sent after commit) or `failed` (nothing imported).
    Disconnecting before the import is committed rolls it back. A stream that ends without `completed` or `failed`
    (connection lost) has an unknown outcome: the commit may have happened just before the drop.
    """
    summary: ImportSummaryRead | None = None
    try:
        # Own transaction instead of SessionDep: it must be committed before `completed` goes out.
        async with sessionmaker() as session, session.begin():
            async for item in service.import_events(session, upload.content, upload.fmt):
                if isinstance(item, ImportSummaryRead):
                    summary = item
                else:
                    yield item
    except DomainError as e:
        log.info("imports.failed", message=str(e), error=type(e).__name__, format=upload.fmt)
        status_code, detail = error_body(e)
        yield ImportFailed.model_validate({"status": status_code, "detail": detail})
        return
    except Exception:
        # The status is already 200: without a terminal event the client can't tell this from a dropped connection.
        log.exception("imports.crashed", message="Import failed unexpectedly", format=upload.fmt)
        yield ImportFailed(status=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Import failed unexpectedly")
        return
    assert summary is not None, "service yields a summary last"
    log.info("imports.completed", message="LARPing events imported", format=upload.fmt, **summary.model_dump())
    yield ImportCompleted(summary=summary)
