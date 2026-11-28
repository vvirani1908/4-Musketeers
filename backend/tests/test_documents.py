import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, literal
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key")

from app.auth import hash_password  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Document, DocumentChunk, User, UserRole  # noqa: E402


PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PDF_BYTES_DIFFERENT = b"%PDF-1.7\n2 0 obj\n<< /Title (Different) >>\nendobj\n%%EOF\n"


class DocumentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(bind=cls.engine)
        cls.storage = tempfile.TemporaryDirectory()
        cls.previous_storage_path = os.environ.get("DOCUMENT_STORAGE_PATH")
        os.environ["DOCUMENT_STORAGE_PATH"] = cls.storage.name
        cls.client = TestClient(app)
        app.dependency_overrides[get_db] = cls.override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.client.close()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()
        cls.storage.cleanup()
        if cls.previous_storage_path is None:
            os.environ.pop("DOCUMENT_STORAGE_PATH", None)
        else:
            os.environ["DOCUMENT_STORAGE_PATH"] = cls.previous_storage_path

    @classmethod
    def override_get_db(cls):
        with cls.session_factory() as db:
            yield db

    def setUp(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all(
                [
                    User(
                        email="admin@example.com",
                        password_hash=hash_password("Admin-test-password"),
                        role=UserRole.ADMIN,
                    ),
                    User(
                        email="employee@example.com",
                        password_hash=hash_password("Employee-test-password"),
                        role=UserRole.EMPLOYEE,
                    ),
                ]
            )
            db.commit()
        for path in Path(self.storage.name).iterdir():
            path.unlink()

    def login(self, email: str, password: str) -> str:
        response = self.client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_admin_can_upload_list_download_and_delete_pdf(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.documents.process_document_in_background"):
            upload = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("../../quarterly-report.pdf", PDF_BYTES, "application/pdf")},
            )
        self.assertEqual(upload.status_code, 201)
        document = upload.json()
        self.assertEqual(document["filename"], "quarterly-report.pdf")

        stored_files = list(Path(self.storage.name).glob("*.pdf"))
        self.assertEqual(len(stored_files), 1)
        self.assertNotEqual(stored_files[0].name, document["filename"])

        listing = self.client.get("/api/documents", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()[0]["id"], document["id"])

        download = self.client.get(
            f"/api/documents/{document['id']}/download",
            headers=headers,
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, PDF_BYTES)
        self.assertIn("quarterly-report.pdf", download.headers["content-disposition"])

        deleted = self.client.delete(f"/api/documents/{document['id']}", headers=headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/documents", headers=headers).json(), [])
        self.assertEqual(list(Path(self.storage.name).glob("*")), [])

    def test_upload_schedules_automatic_indexing(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        with patch("app.documents.process_document_in_background") as process_document:
            upload = self.client.post(
                "/api/documents",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("scheduled.pdf", PDF_BYTES, "application/pdf")},
            )
        self.assertEqual(upload.status_code, 201)
        self.assertEqual(upload.json()["processing_status"], "indexing")
        process_document.assert_called_once()
        self.assertEqual(process_document.call_args.args[0], upload.json()["id"])

    def test_identical_pdf_content_is_rejected_even_with_a_different_filename(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.documents.process_document_in_background") as process_document:
            first = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("first-name.pdf", PDF_BYTES, "application/pdf")},
            )
            duplicate = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("different-name.pdf", PDF_BYTES, "application/pdf")},
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "This PDF has already been uploaded.")
        self.assertEqual(process_document.call_count, 1)
        self.assertEqual(len(self.client.get("/api/documents", headers=headers).json()), 1)

    def test_same_filename_with_different_content_is_allowed(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.documents.process_document_in_background"):
            first = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("same-name.pdf", PDF_BYTES, "application/pdf")},
            )
            second = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("same-name.pdf", PDF_BYTES_DIFFERENT, "application/pdf")},
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(len(self.client.get("/api/documents", headers=headers).json()), 2)

    def test_mixed_duplicate_and_new_uploads_preserve_only_new_record(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.documents.process_document_in_background") as process_document:
            first = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("existing.pdf", PDF_BYTES, "application/pdf")},
            )
            duplicate = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("existing-copy.pdf", PDF_BYTES, "application/pdf")},
            )
            new_upload = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("new.pdf", PDF_BYTES_DIFFERENT, "application/pdf")},
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(new_upload.status_code, 201)
        self.assertEqual(process_document.call_count, 2)
        self.assertEqual(len(self.client.get("/api/documents", headers=headers).json()), 2)

    def test_failed_reindex_preserves_existing_index_but_initial_failure_is_failed(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.documents.process_document_in_background"):
            upload = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("reindex-safe.pdf", PDF_BYTES, "application/pdf")},
            )
        document_id = upload.json()["id"]

        with Session(self.engine) as db:
            document = db.get(Document, document_id)
            document.processing_status = "indexed"
            db.add(DocumentChunk(
                document_id=document_id,
                chunk_index=0,
                page_number=1,
                content="Previously indexed content remains searchable.",
                embedding=[0.1] * 384,
            ))
            db.commit()

        with patch("app.documents.index_document", side_effect=ValueError("new embedding failed")):
            failed_reindex = self.client.post(f"/api/documents/{document_id}/index", headers=headers)
        self.assertEqual(failed_reindex.status_code, 200)
        self.assertEqual(failed_reindex.json()["processing_status"], "indexed")
        with Session(self.engine) as db:
            document = db.get(Document, document_id)
            self.assertEqual(document.processing_status, "indexed")
            self.assertEqual(document.processing_error, None)
            self.assertEqual(
                db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).one().content,
                "Previously indexed content remains searchable.",
            )

        with Session(self.engine) as db:
            document = db.get(Document, document_id)
            document.processing_status = "indexing"
            db.commit()
        with patch("app.documents.index_document", side_effect=ValueError("initial embedding failed")):
            failed_initial = self.client.post(f"/api/documents/{document_id}/index", headers=headers)
        self.assertEqual(failed_initial.status_code, 200)
        self.assertEqual(failed_initial.json()["processing_status"], "failed")

    def test_employee_can_list_and_download_but_not_upload_or_delete(self) -> None:
        admin_token = self.login("admin@example.com", "Admin-test-password")
        with patch("app.documents.process_document_in_background"):
            upload = self.client.post(
                "/api/documents",
                headers={"Authorization": f"Bearer {admin_token}"},
                files={"file": ("policy.pdf", PDF_BYTES, "application/pdf")},
            )
        document_id = upload.json()["id"]

        employee_token = self.login("employee@example.com", "Employee-test-password")
        employee_headers = {"Authorization": f"Bearer {employee_token}"}
        self.assertEqual(self.client.get("/api/documents", headers=employee_headers).status_code, 200)
        class FakeEmbedding:
            def tolist(self):
                return [0.0] * 384

        class FakeModel:
            def encode(self, *_args, **_kwargs):
                return [FakeEmbedding()]

        with patch("app.documents.get_embedding_model", return_value=FakeModel()), patch.object(
            DocumentChunk.embedding.type.comparator_factory,
            "cosine_distance",
            return_value=literal(0.0),
        ):
            self.assertEqual(
                self.client.get(
                    "/api/documents/search?q=policy",
                    headers=employee_headers,
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.get(
                f"/api/documents/{document_id}/download",
                headers=employee_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/documents",
                headers=employee_headers,
                files={"file": ("employee.pdf", PDF_BYTES, "application/pdf")},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/documents/{document_id}", headers=employee_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/api/documents/{document_id}/index", headers=employee_headers).status_code,
            403,
        )

    def test_invalid_and_oversized_uploads_leave_no_files_or_records(self) -> None:
        token = self.login("admin@example.com", "Admin-test-password")
        headers = {"Authorization": f"Bearer {token}"}

        invalid = self.client.post(
            "/api/documents",
            headers=headers,
            files={"file": ("notes.txt", b"not a PDF", "text/plain")},
        )
        self.assertEqual(invalid.status_code, 400)

        previous_limit = os.environ.get("DOCUMENT_MAX_SIZE_BYTES")
        os.environ["DOCUMENT_MAX_SIZE_BYTES"] = "8"
        try:
            oversized = self.client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("large.pdf", PDF_BYTES, "application/pdf")},
            )
        finally:
            if previous_limit is None:
                os.environ.pop("DOCUMENT_MAX_SIZE_BYTES", None)
            else:
                os.environ["DOCUMENT_MAX_SIZE_BYTES"] = previous_limit

        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(self.client.get("/api/documents", headers=headers).json(), [])
        self.assertEqual(list(Path(self.storage.name).glob("*")), [])


if __name__ == "__main__":
    unittest.main()
