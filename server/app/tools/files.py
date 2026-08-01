from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import zipfile

from fastapi import UploadFile


MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_XLSX_ENTRIES = 4096
MAX_XLSX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".xlsx", ".xls"}
_XLSX_ZIP_SIGNATURE = b"PK\x03\x04"
_XLS_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_XLSX_REQUIRED_ENTRIES = {"[Content_Types].xml", "xl/workbook.xml"}
ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # browsers often use this for local CSV/XLSX files
}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SavedUpload:
    filename: str
    path: Path
    content_type: str | None
    size_bytes: int


def _validate_upload_metadata(file: UploadFile) -> tuple[str, str]:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_SUFFIXES))
        raise UploadValidationError(f"Unsupported file type. Allowed extensions: {allowed}")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type: {content_type}")

    return filename, suffix


def _validate_saved_upload(path: Path, suffix: str) -> None:
    """Reject only clearly invalid content without blocking normal Excel/CSV uploads."""
    if suffix == ".csv":
        with path.open("rb") as handle:
            sample = handle.read(4096)
        if b"\x00" in sample:
            raise UploadValidationError("Invalid CSV file content")
    elif suffix == ".xlsx":
        _validate_xlsx_structure(path)
    elif suffix == ".xls":
        _validate_xls_signature(path)


def _validate_xlsx_structure(path: Path) -> None:
    """Validate that a .xlsx upload is a bounded, structurally sound OOXML container."""
    with path.open("rb") as handle:
        signature = handle.read(4)
    if signature != _XLSX_ZIP_SIGNATURE:
        raise UploadValidationError("Invalid XLSX file content: not a ZIP container")

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_XLSX_ENTRIES:
                raise UploadValidationError("Invalid XLSX file content: too many archive entries")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise UploadValidationError("Invalid XLSX file content: archive too large")
            names = {info.filename for info in infos}
            missing = sorted(_XLSX_REQUIRED_ENTRIES - names)
            if missing:
                raise UploadValidationError(
                    "Invalid XLSX file content: missing required entries "
                    f"({', '.join(missing)})"
                )
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("Invalid XLSX file content: corrupted ZIP") from exc


def _validate_xls_signature(path: Path) -> None:
    """Validate that a legacy .xls upload starts with an OLE2 compound-file signature."""
    with path.open("rb") as handle:
        signature = handle.read(8)
    if signature != _XLS_OLE_SIGNATURE:
        raise UploadValidationError("Invalid XLS file content: missing OLE2 signature")


async def save_upload(
    file: UploadFile,
    upload_dir: Path,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> SavedUpload:
    filename, suffix = _validate_upload_metadata(file)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid4().hex}{suffix}"
    path = upload_dir / safe_name
    total_bytes = 0

    try:
        with path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise UploadValidationError(
                        f"File too large. Max upload size is {max_bytes // (1024 * 1024)} MB"
                    )
                handle.write(chunk)
        _validate_saved_upload(path, suffix)
    except Exception:
        if path.exists():
            path.unlink(missing_ok=True)
        raise

    return SavedUpload(
        filename=filename,
        path=path,
        content_type=file.content_type,
        size_bytes=total_bytes,
    )
