import io

import openpyxl
import pytest
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.tools.files import UploadValidationError, save_upload


def upload_file(filename: str, content: bytes, content_type: str):
    return StarletteUploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def _valid_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["id", "total"])
    sheet.append([1, 10])
    workbook.save(buffer)
    return buffer.getvalue()


def _valid_xls_bytes() -> bytes:
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 128


@pytest.mark.anyio
async def test_save_upload_accepts_csv(tmp_path):
    file = upload_file("orders.csv", b"id,total\n1,10\n", "text/csv")
    saved = await save_upload(file, tmp_path)
    assert saved.filename == "orders.csv"
    assert saved.path.exists()
    assert saved.path.suffix == ".csv"
    assert saved.size_bytes > 0


@pytest.mark.anyio
async def test_save_upload_accepts_excel_extensions(tmp_path):
    for filename, content_type in [
        ("orders.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("orders.xls", "application/vnd.ms-excel"),
    ]:
        content = _valid_xlsx_bytes() if filename.endswith(".xlsx") else _valid_xls_bytes()
        file = upload_file(filename, content, content_type)
        saved = await save_upload(file, tmp_path)
        assert saved.filename == filename
        assert saved.path.exists()
        assert saved.path.suffix == f".{filename.rsplit('.', 1)[1]}"


@pytest.mark.anyio
async def test_save_upload_rejects_fake_xlsx(tmp_path):
    file = upload_file(
        "orders.xlsx",
        b"excel workbook bytes",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    with pytest.raises(UploadValidationError, match="Invalid XLSX"):
        await save_upload(file, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_save_upload_rejects_xlsx_missing_required_entries(tmp_path):
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    file = upload_file(
        "orders.xlsx",
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    with pytest.raises(UploadValidationError, match="missing required entries"):
        await save_upload(file, tmp_path)


@pytest.mark.anyio
async def test_save_upload_rejects_fake_xls(tmp_path):
    file = upload_file("orders.xls", b"not an ole file", "application/vnd.ms-excel")
    with pytest.raises(UploadValidationError, match="Invalid XLS"):
        await save_upload(file, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_save_upload_rejects_unsupported_extension(tmp_path):
    file = upload_file("orders.txt", b"hello", "text/plain")
    with pytest.raises(UploadValidationError, match="Unsupported file type"):
        await save_upload(file, tmp_path)


@pytest.mark.anyio
async def test_save_upload_rejects_oversized_file_and_cleans_partial(tmp_path):
    file = upload_file("orders.csv", b"x" * 8, "text/csv")
    with pytest.raises(UploadValidationError, match="File too large"):
        await save_upload(file, tmp_path, max_bytes=4)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_save_upload_rejects_binary_csv_and_cleans_partial(tmp_path):
    file = upload_file("orders.csv", b"id\x00total\n1\x002\n", "text/csv")
    with pytest.raises(UploadValidationError, match="Invalid CSV"):
        await save_upload(file, tmp_path)
    assert list(tmp_path.iterdir()) == []
