import logging
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Document, User, UserRole
from app.schemas import DocumentResponse


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])
PDF_SIGNATURE = b"%PDF-"
CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


def get_storage_directory() -> Path:
    """Return the resolved local directory used for uploaded documents."""
    configured_path = os.getenv("DOCUMENT_STORAGE_PATH", "storage/documents")
    storage_path = Path(configured_path)
    if not storage_path.is_absolute():
        storage_path = Path(__file__).resolve().parents[1] / storage_path
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path.resolve()


def get_max_file_size() -> int:
    return int(os.getenv("DOCUMENT_MAX_SIZE_BYTES", str(DEFAULT_MAX_FILE_SIZE)))


def safe_original_filename(filename: str | None) -> str:
    """Keep only a display name and reject empty or non-PDF filenames."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    return name


def document_path(document: Document) -> Path:
    """Resolve a stored filename while preventing path traversal."""
    storage_directory = get_storage_directory()
    candidate = (storage_directory / document.storage_path).resolve()
    try:
        candidate.relative_to(storage_directory)
    except ValueError:
        raise HTTPException(status_code=500, detail="Invalid document storage path") from None
    return candidate


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> Document:
    """Validate and store a PDF, then persist its metadata."""
    filename = safe_original_filename(file.filename)
    storage_directory = get_storage_directory()
    temporary_path: Path | None = None
    final_path: Path | None = None
    database_committed = False

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=storage_directory,
            prefix=".upload-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            total_size = 0
            first_bytes = b""
            while chunk := await file.read(CHUNK_SIZE):
                if not first_bytes:
                    first_bytes = chunk[: len(PDF_SIGNATURE)]
                total_size += len(chunk)
                if total_size > get_max_file_size():
                    raise HTTPException(status_code=413, detail="PDF exceeds the maximum allowed size")
                temporary_file.write(chunk)

        if first_bytes != PDF_SIGNATURE:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

        generated_filename = f"{uuid4().hex}.pdf"
        final_path = storage_directory / generated_filename
        temporary_path.replace(final_path)
        temporary_path = None

        document = Document(
            filename=filename,
            storage_path=generated_filename,
            uploaded_by=current_user.id,
        )
        db.add(document)
        db.commit()
        database_committed = True
        db.refresh(document)
        return document
    except HTTPException:
        db.rollback()
        raise
    except (OSError, SQLAlchemyError):
        db.rollback()
        logger.exception("Failed to store uploaded document")
        raise HTTPException(status_code=500, detail="Could not store document") from None
    finally:
        await file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if final_path is not None and not database_committed:
            final_path.unlink(missing_ok=True)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    """List document metadata for authenticated users."""
    return list(db.scalars(select(Document).order_by(Document.created_at.desc(), Document.id.desc())))


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a stored document for authenticated users."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = document_path(document)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")
    return FileResponse(path, media_type="application/pdf", filename=document.filename)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    """Delete document metadata and its local file."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = document_path(document)
    db.delete(document)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Document metadata deleted but file cleanup failed: %s", path)
