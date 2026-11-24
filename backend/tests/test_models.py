import unittest

from sqlalchemy import Enum as SqlEnum, inspect

from app.database import Base
from app.models import Document, DocumentChunk, User, UserRole


class ModelTests(unittest.TestCase):
    def test_models_are_registered_with_metadata(self) -> None:
        self.assertEqual(set(Base.metadata.tables), {"users", "documents", "document_chunks"})

    def test_user_columns_and_constraints(self) -> None:
        table = User.__table__

        self.assertTrue(table.c.id.primary_key)
        self.assertTrue(table.c.email.unique)
        self.assertFalse(table.c.email.nullable)
        self.assertFalse(table.c.password_hash.nullable)
        self.assertFalse(table.c.role.nullable)
        self.assertFalse(table.c.created_at.nullable)
        self.assertIsInstance(table.c.role.type, SqlEnum)
        self.assertEqual(set(table.c.role.type.enums), {"admin", "employee"})

    def test_document_columns_and_foreign_key(self) -> None:
        table = Document.__table__

        self.assertTrue(table.c.id.primary_key)
        self.assertFalse(table.c.filename.nullable)
        self.assertFalse(table.c.storage_path.nullable)
        self.assertFalse(table.c.uploaded_by.nullable)
        self.assertFalse(table.c.created_at.nullable)
        self.assertFalse(table.c.processing_status.nullable)
        self.assertTrue(table.c.processing_error.nullable)
        foreign_key = next(iter(table.c.uploaded_by.foreign_keys))
        self.assertEqual(foreign_key.target_fullname, "users.id")

    def test_user_document_relationship(self) -> None:
        self.assertIs(User.documents.property.mapper.class_, Document)
        self.assertIs(Document.uploader.property.mapper.class_, User)
        self.assertEqual(User.documents.property.back_populates, "uploader")
        self.assertEqual(Document.uploader.property.back_populates, "documents")
        self.assertIs(Document.chunks.property.mapper.class_, DocumentChunk)

    def test_role_values(self) -> None:
        self.assertEqual(UserRole.ADMIN.value, "admin")
        self.assertEqual(UserRole.EMPLOYEE.value, "employee")


if __name__ == "__main__":
    unittest.main()
