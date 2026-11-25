import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, literal
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_db
from app.llm import CohereProvider, GeminiProvider, LLMConfigurationError, LLMProviderError, get_llm_provider
from app.main import app
from app.models import Document, DocumentChunk, User, UserRole


class FakeEmbedding:
    def tolist(self):
        return [0.0] * 384


class FakeEmbeddingModel:
    def encode(self, *_args, **_kwargs):
        return [FakeEmbedding()]


class FakeProvider:
    def __init__(self, answer="Grounded answer"):
        self.answer = answer
        self.provider = "gemini"
        self.model = "gemini-3.5-flash-lite"
        self.calls = []

    def generate(self, system, prompt):
        self.calls.append((system, prompt))
        return self.answer


class RAGApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.session_factory = sessionmaker(bind=cls.engine)
        cls.client = TestClient(app)
        app.dependency_overrides[get_db] = cls.override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.client.close()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    @classmethod
    def override_get_db(cls):
        with cls.session_factory() as db:
            yield db

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            user = User(email="employee@example.com", password_hash=hash_password("Employee-test-password"), role=UserRole.EMPLOYEE)
            db.add(user)
            db.flush()
            document = Document(filename="handbook.pdf", storage_path="handbook.pdf", uploaded_by=user.id, processing_status="indexed")
            db.add(document)
            db.flush()
            db.add(DocumentChunk(document_id=document.id, chunk_index=0, page_number=7, content="Employees may work remotely on Fridays.", embedding=[0.0] * 384))
            db.commit()

    def token(self):
        response = self.client.post("/api/auth/login", data={"username": "employee@example.com", "password": "Employee-test-password"})
        return response.json()["access_token"]

    def request(self, question="When may employees work remotely?"):
        return self.client.post("/api/rag/ask", headers={"Authorization": f"Bearer {self.token()}"}, json={"question": question})

    def retrieval_patch(self):
        return patch("app.rag.get_embedding_model", return_value=FakeEmbeddingModel()), patch.object(
            DocumentChunk.embedding.type.comparator_factory, "cosine_distance", return_value=literal(0.1)
        )

    def test_employee_can_receive_grounded_answer_and_sources(self):
        provider = FakeProvider()
        embedding, distance = self.retrieval_patch()
        with embedding, distance, patch("app.rag.get_llm_provider", return_value=provider):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"][0]["filename"], "handbook.pdf")
        self.assertEqual(response.json()["sources"][0]["page_number"], 7)
        self.assertEqual(response.json()["provider"], "gemini")
        self.assertEqual(response.json()["model"], "gemini-3.5-flash-lite")
        self.assertIn("handbook.pdf", provider.calls[0][1])

    def test_insufficient_context_does_not_call_llm(self):
        provider = FakeProvider()
        embedding, distance = self.retrieval_patch()
        with embedding, distance, patch("app.rag.get_llm_provider", return_value=provider), patch.dict(os.environ, {"RAG_MIN_SIMILARITY": "0.99"}):
            response = self.request("What is the travel budget?")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])
        self.assertIn("couldn't find enough", response.json()["answer"])
        self.assertEqual(provider.calls, [])

    def test_missing_api_key_is_reported(self):
        embedding, distance = self.retrieval_patch()
        with embedding, distance, patch.dict(os.environ, {"LLM_PROVIDER": "cohere", "COHERE_API_KEY": ""}), patch("app.rag.get_llm_provider", side_effect=LLMConfigurationError("COHERE_API_KEY is required")):
            response = self.request()
        self.assertEqual(response.status_code, 503)

    def test_provider_failure_is_reported(self):
        embedding, distance = self.retrieval_patch()
        with embedding, distance, patch("app.rag.get_llm_provider", side_effect=LLMProviderError("failed")):
            response = self.request()
        self.assertEqual(response.status_code, 502)


class ProviderAdapterTests(unittest.TestCase):
    def test_provider_selection_exposes_configured_metadata(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "cohere", "COHERE_API_KEY": "key", "COHERE_MODEL": "command-a-03-2025"}):
            cohere = get_llm_provider()
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "key", "GEMINI_MODEL": "gemini-3.5-flash-lite"}):
            gemini = get_llm_provider()
        self.assertEqual((cohere.provider, cohere.model), ("cohere", "command-a-03-2025"))
        self.assertEqual((gemini.provider, gemini.model), ("gemini", "gemini-3.5-flash-lite"))

    def test_cohere_adapter_uses_mocked_chat_response(self):
        client = SimpleNamespace(chat=lambda **_: SimpleNamespace(message=SimpleNamespace(content=[SimpleNamespace(type="text", text="Cohere answer")])))
        with patch.dict("sys.modules", {"cohere": SimpleNamespace(ClientV2=lambda **_: client)}):
            self.assertEqual(CohereProvider("key", "model").generate("system", "question"), "Cohere answer")

    def test_gemini_adapter_uses_mocked_generate_response(self):
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text="Gemini answer")))
        genai = SimpleNamespace(Client=lambda **_: client)
        with patch.dict("sys.modules", {"google": SimpleNamespace(genai=genai), "google.genai": genai}):
            self.assertEqual(GeminiProvider("key", "model").generate("system", "question"), "Gemini answer")


if __name__ == "__main__":
    unittest.main()
