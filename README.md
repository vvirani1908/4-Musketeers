# AI-Powered Enterprise Knowledge Portal

CMPE 272 team project by 4-Musketeers. This repository contains the portal's full-stack foundation, including PostgreSQL/pgvector integration, SQLAlchemy models and migrations, authentication, role-based access control, local PDF processing, and semantic search. RAG-based question answering is intentionally not included.

## Project structure

```text
.
├── backend/       # FastAPI service
│   ├── app/
│   └── requirements.txt
├── frontend/      # React + Vite application
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml # Local PostgreSQL + pgvector service
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.12 (supported local development and test environment)
- Node.js 18 or newer and npm
- Docker with Docker Compose

## Local setup

From the repository root, create and activate a backend virtual environment, then install the Python dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Configure and start the backend in that terminal:

```bash
cp .env.example .env
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend reads `DATABASE_URL` from the local `.env` file. The example points to the PostgreSQL Compose service and contains development-only credentials.

The backend provides `POST /api/auth/login` and `GET /api/auth/me` using bearer tokens. Create a local test user interactively so the password is never placed in shell history or source files:

```bash
python -m app.create_test_user --email employee@example.com --role employee
python -m app.create_test_user --email admin@example.com --role admin
```

The command prompts for and confirms each password. Role checks are reusable for protected endpoints through the `require_roles(...)` dependency.

Apply database migrations from the backend directory:

```bash
alembic upgrade head
alembic current
```

The migrations create the `users`, `documents`, and `document_chunks` tables, the `user_role` enum, and the pgvector extension/index.

## Document management

Authenticated users can list and download PDF documents. Admin users can also upload and delete them; employee users have read-only access. Uploaded files are stored locally under `backend/storage/documents` by default, while metadata is stored in PostgreSQL. The storage directory is ignored by Git.

The API provides:

- `POST /api/documents` — admin-only PDF upload
- `GET /api/documents` — authenticated document metadata listing
- `GET /api/documents/{document_id}/download` — authenticated PDF download
- `DELETE /api/documents/{document_id}` — admin-only deletion
- `GET /api/documents/search?q=...` — authenticated semantic search with snippets, pages, and similarity scores
- `POST /api/documents/index` — admin-only indexing of older/unindexed documents
- `POST /api/documents/{document_id}/index` — admin-only retry/re-index of one document

Uploads use generated filenames, preserve the original filename as metadata, reject non-PDF content, and enforce a 10 MB default limit. After the document record is committed, the API marks it `indexing` and schedules local processing automatically; the background worker extracts text with `pypdf`, splits it into overlapping word chunks, and embeds it with `all-MiniLM-L6-v2` (384 dimensions). The first indexing run downloads that model into the normal local Hugging Face cache; no paid API or API key is used. Processing status is `pending`, `indexing`, `indexed`, or `failed`; processing failure does not remove the uploaded document. The React app refreshes pending/indexing documents until a terminal state is reached.

Deleting a document cascades to its chunks and embeddings. Empty, image-only, corrupt, or unreadable PDFs are retained with `processing_status=failed`. Re-indexing builds embeddings before replacing existing chunks, so a successful existing index remains intact if a retry fails.

Search returns at most five results, filters out scores below `0.35`, and suppresses highly overlapping chunks from the same document page. Similarity is cosine similarity in the range 0–1, where 1 means the normalized query and chunk embeddings are identical; the score is a relevance signal, not a probability.

In a second terminal, install and start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. The frontend requests `/api/health`; Vite proxies that request to the FastAPI service at `http://127.0.0.1:8000`.

The backend health endpoint can also be checked directly:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected response:

```json
{"status":"ok"}
```

## Local PostgreSQL + pgvector

The database foundation uses Docker Compose, stores data in the named `postgres_data` volume, and binds PostgreSQL to localhost only. The example credentials are for local development only.

Start the database from the repository root:

```bash
docker compose up -d postgres
```

Check that the container is healthy:

```bash
docker compose ps
```

Verify PostgreSQL and the `vector` extension:

```bash
docker compose exec postgres pg_isready -U knowledge_portal -d knowledge_portal
docker compose exec postgres psql -U knowledge_portal -d knowledge_portal -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

Stop the database while preserving its data:

```bash
docker compose stop postgres
```

To stop and remove the container while keeping the persistent volume, use `docker compose down`. Removing the volume is destructive and is not needed for normal development.

## Environment configuration

Example files are provided at the root, `backend/.env.example`, and `frontend/.env.example`. They contain no credentials. Copy values into local environment files only when needed; local `.env` files are ignored by Git.

## Current scope

This iteration includes the frontend shell, backend health endpoint, development proxy, local PostgreSQL/pgvector foundation, SQLAlchemy User, Document, and DocumentChunk models, Alembic migrations, JWT authentication, admin/employee role-based access control, local PDF document management, PDF extraction, local embeddings, and semantic search. LLM-generated answers, RAG, and chat history remain out of scope.
