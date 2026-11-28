"""Local PDF extraction, chunking, and sentence-transformer indexing."""

from functools import lru_cache
from pathlib import Path
import re
from threading import Lock

from pypdf import PdfReader
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import logging

from app.models import Document, DocumentChunk

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
CHUNK_WORDS = 220
CHUNK_OVERLAP_WORDS = 40
logger = logging.getLogger(__name__)
_embedding_model_lock = Lock()
_indexing_lock = Lock()


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Extract non-empty page text while retaining one-based page numbers."""
    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((page_number, text))
    if not pages:
        raise ValueError("PDF contains no extractable text")
    return pages


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_words: int = CHUNK_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[tuple[int, str]]:
    """Split page text into overlapping word chunks, preserving the source page."""
    if chunk_words <= overlap_words:
        raise ValueError("chunk_words must be greater than overlap_words")
    chunks: list[tuple[int, str]] = []
    step = chunk_words - overlap_words
    for page_number, text in pages:
        words = re.findall(r"\S+", text)
        for start in range(0, len(words), step):
            content = " ".join(words[start : start + chunk_words]).strip()
            if content:
                chunks.append((page_number, content))
            if start + chunk_words >= len(words):
                break
    return chunks


@lru_cache(maxsize=1)
def _load_embedding_model():
    # Import lazily so PDF validation and normal API startup do not initialize torch.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def get_embedding_model():
    """Return the shared embedding model, initializing it at most once at a time."""
    # lru_cache protects its internal data structure, but concurrent cache misses
    # can still execute the wrapped factory more than once. SentenceTransformer
    # initialization mutates torch modules, so serialize the first construction.
    with _embedding_model_lock:
        return _load_embedding_model()


def index_document(db: Session, document: Document, path: Path) -> int:
    """Serialize document indexing so model inference and DB replacement stay safe."""
    with _indexing_lock:
        return _index_document(db, document, path)


def _index_document(db: Session, document: Document, path: Path) -> int:
    """Extract, embed, and atomically replace a document's chunks."""
    chunks = chunk_pages(extract_pdf_pages(path))
    texts = [content for _, content in chunks]
    embeddings = get_embedding_model().encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    )
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.add_all(
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            page_number=page_number,
            content=content,
            embedding=embedding.tolist(),
        )
        for index, ((page_number, content), embedding) in enumerate(zip(chunks, embeddings))
    )
    document.processing_status = "indexed"
    document.processing_error = None
    db.commit()
    return len(chunks)


def mark_processing_failed(db: Session, document: Document, error: Exception) -> None:
    db.rollback()
    document = db.get(Document, document.id)
    if document is not None:
        document.processing_status = "failed"
        document.processing_error = str(error)[:2000]
        db.commit()


def process_document_in_background(document_id: int, storage_path: str) -> None:
    """Process one committed document using a fresh request-independent session."""
    from app.database import SessionLocal, engine

    if engine is None:
        return
    try:
        with SessionLocal(bind=engine) as db:
            document = db.get(Document, document_id)
            if document is None:
                return
            index_document(db, document, Path(storage_path))
    except (OSError, SQLAlchemyError) as error:
        logger.exception("Background indexing could not access document %s", document_id)
    except Exception as error:
        logger.exception("Background indexing failed for document %s", document_id)
        try:
            with SessionLocal(bind=engine) as db:
                document = db.get(Document, document_id)
                if document is not None:
                    mark_processing_failed(db, document, error)
        except (OSError, SQLAlchemyError):
            logger.exception("Could not persist indexing failure for document %s", document_id)
