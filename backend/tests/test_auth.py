import os
import unittest
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key")

from app.auth import hash_password  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(bind=cls.engine)
        cls.client = TestClient(app)
        app.dependency_overrides[get_db] = cls.override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.client.close()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

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

    def login(self, email: str, password: str) -> str:
        response = self.client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_successful_login_and_current_user(self) -> None:
        token = self.login("employee@example.com", "Employee-test-password")

        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "employee@example.com")
        self.assertEqual(response.json()["role"], "employee")

    def test_invalid_credentials_are_rejected(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            data={"username": "employee@example.com", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self) -> None:
        expired_token = jwt.encode(
            {
                "sub": "2",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            os.environ["JWT_SECRET_KEY"],
            algorithm="HS256",
        )

        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_token_is_rejected(self) -> None:
        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )

        self.assertEqual(response.status_code, 401)

    def test_admin_role_is_required(self) -> None:
        employee_token = self.login("employee@example.com", "Employee-test-password")
        employee_response = self.client.get(
            "/api/auth/admin-check",
            headers={"Authorization": f"Bearer {employee_token}"},
        )
        self.assertEqual(employee_response.status_code, 403)

        admin_token = self.login("admin@example.com", "Admin-test-password")
        admin_response = self.client.get(
            "/api/auth/admin-check",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json()["role"], "admin")


if __name__ == "__main__":
    unittest.main()
