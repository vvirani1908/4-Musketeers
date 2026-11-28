import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, DocumentChunk, User
from app.processing import chunk_pages, extract_pdf_pages, get_embedding_model, index_document, mark_processing_failed


class PdfProcessingTests(unittest.TestCase):
    def test_embedding_model_initialization_is_singleton_under_concurrency(self) -> None:
        model = object()
        initialization_count = 0

        def load_model(*_args, **_kwargs):
            nonlocal initialization_count
            initialization_count += 1
            sleep(0.02)
            return model

        from app.processing import _load_embedding_model

        _load_embedding_model.cache_clear()
        try:
            with patch("sentence_transformers.SentenceTransformer", side_effect=load_model):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    models = list(executor.map(lambda _: get_embedding_model(), range(8)))
            self.assertEqual(initialization_count, 1)
            self.assertTrue(all(candidate is model for candidate in models))
        finally:
            _load_embedding_model.cache_clear()

    def test_concurrent_indexing_operations_are_serialized(self) -> None:
        active_operations = 0
        maximum_active_operations = 0

        def fake_index(*_args):
            nonlocal active_operations, maximum_active_operations
            active_operations += 1
            maximum_active_operations = max(maximum_active_operations, active_operations)
            sleep(0.02)
            active_operations -= 1
            return 1

        with patch("app.processing._index_document", side_effect=fake_index):
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda _: index_document(None, None, Path("ignored.pdf")), range(2)))
        self.assertEqual(maximum_active_operations, 1)

    def test_extract_pdf_pages_keeps_one_based_page_numbers(self) -> None:
        class FakePage:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        class FakeReader:
            pages = [FakePage("first page"), FakePage(""), FakePage("third page")]

        with patch("app.processing.PdfReader", return_value=FakeReader()):
            self.assertEqual(extract_pdf_pages("example.pdf"), [(1, "first page"), (3, "third page")])

    def test_chunking_overlaps_words_and_preserves_page(self) -> None:
        pages = [(2, "one two three four five six seven eight nine ten")]
        chunks = chunk_pages(pages, chunk_words=5, overlap_words=2)
        self.assertEqual([page for page, _ in chunks], [2, 2, 2])
        self.assertEqual(chunks[0][1], "one two three four five")
        self.assertEqual(chunks[1][1], "four five six seven eight")
        self.assertEqual(chunks[2][1], "seven eight nine ten")

    def test_invalid_chunk_parameters_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunk_pages([(1, "text")], chunk_words=4, overlap_words=4)

    def test_indexing_replaces_chunks_and_stores_page_and_embedding(self) -> None:
        class FakePage:
            def extract_text(self):
                return "A searchable policy statement."

        class FakeReader:
            pages = [FakePage()]

        class FakeEmbedding:
            def tolist(self):
                return [0.1] * 384

        class FakeModel:
            def encode(self, texts, **_kwargs):
                return [FakeEmbedding() for _ in texts]

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with TemporaryDirectory() as directory, Session(engine) as db:
            user = User(email="index@example.com", password_hash="hash")
            db.add(user)
            db.flush()
            document = Document(filename="policy.pdf", storage_path="policy.pdf", uploaded_by=user.id)
            db.add(document)
            db.commit()
            with patch("app.processing.PdfReader", return_value=FakeReader()), patch(
                "app.processing.get_embedding_model", return_value=FakeModel()
            ):
                self.assertEqual(index_document(db, document, Path(directory) / "policy.pdf"), 1)
            stored = db.scalars(select(DocumentChunk)).all()
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].page_number, 1)
            self.assertEqual(len(stored[0].embedding), 384)
            db.delete(document)
            db.commit()
            self.assertEqual(db.scalars(select(DocumentChunk)).all(), [])

    def test_unreadable_pdf_is_recorded_as_failed_without_chunks(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with TemporaryDirectory() as directory, Session(engine) as db:
            user = User(email="failed@example.com", password_hash="hash")
            db.add(user)
            db.flush()
            document = Document(filename="unreadable.pdf", storage_path="unreadable.pdf", uploaded_by=user.id)
            db.add(document)
            db.commit()
            with self.assertRaises(Exception):
                index_document(db, document, Path(directory) / "unreadable.pdf")
            mark_processing_failed(db, document, ValueError("PDF contains no extractable text"))
            db.refresh(document)
            self.assertEqual(document.processing_status, "failed")
            self.assertIn("no extractable text", document.processing_error)
            self.assertEqual(db.scalars(select(DocumentChunk)).all(), [])


if __name__ == "__main__":
    unittest.main()
