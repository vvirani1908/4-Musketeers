# AI-Powered Enterprise Knowledge Portal

CMPE 272 team project by 4-Musketeers. This repository contains a full-stack enterprise knowledge portal with authenticated PDF management, local indexing, exact pgvector semantic search, and provider-selectable RAG question answering.

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

## Architecture overview

The React/Vite frontend calls the FastAPI backend through the `/api` development proxy. FastAPI handles JWT authentication, admin/employee RBAC, PDF storage, document processing, Semantic Search, and Ask AI. PostgreSQL with pgvector stores users, document metadata, extracted chunks, and 384-dimensional embeddings. PDF extraction and embedding run locally; Ask AI sends retrieved excerpts to the configured Cohere or Gemini provider. The frontend does not receive provider API keys or direct filesystem paths.

## Prerequisites

- Python 3.12 (supported local development and test environment)
- Node.js 20.19 or newer (or 22.12 or newer) and npm; the installed Vite 8 toolchain requires this range
- Docker with Docker Compose

## Initial installation and configuration

From the repository root, create and activate a Python 3.12 backend virtual environment, then install the Python dependencies:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create the local backend configuration from the example. Do not commit the resulting file:

```bash
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Copy the generated value into `JWT_SECRET_KEY` in `backend/.env` (or export it in every backend shell). The backend reads `DATABASE_URL` and other settings from `backend/.env`. The example points to the local PostgreSQL Compose service and contains development-only credentials. Keep API keys only in this ignored file or in the process environment.

Start PostgreSQL from the repository root, then apply migrations from `backend/`:

```bash
cd ..
docker compose up -d postgres
cd backend
alembic upgrade head
alembic current
```

The backend provides `POST /api/auth/login` and `GET /api/auth/me` using bearer tokens. Create a local test user interactively so the password is never placed in shell history or source files:

```bash
python -m app.create_test_user --email employee@example.com --role employee
python -m app.create_test_user --email admin@example.com --role admin
```

The command prompts for and confirms each password so credentials are not placed in shell history or source files. The backend virtual environment and installed dependencies are reused for normal development; repeat the installation only after changing `backend/requirements.txt` or recreating the environment.

## Daily startup and shutdown

From the repository root, start the database and run the backend in one terminal:

```bash
docker compose up -d postgres
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```bash
cd frontend
npm install       # first setup only; use npm ci in CI
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. The frontend proxies `/api` to `http://127.0.0.1:8000` and checks `/api/health`.

To stop daily development without deleting data, stop the processes with Ctrl+C and run:

```bash
docker compose stop postgres
```

The named `postgres_data` volume and uploaded documents remain intact. `docker compose down` also preserves the named volume, but removing the volume is destructive and is not needed for normal shutdown.

The migrations create the `users`, `documents`, and `document_chunks` tables, the `user_role` enum, and the pgvector extension. Migration `0004_exact_vector_search` removes the IVFFlat embedding index for the current small local dataset, so Semantic Search and RAG use exact cosine-distance scans over the stored vectors.

A fresh database contains schema and user tables only; it does not contain demo PDFs or document chunks. Upload public or fictional demo documents through the admin UI after setup.

## Document management

Authenticated users can list and download PDF documents. Admin users can also upload and delete them; employee users have read-only access. The frontend lets admins select multiple PDFs at once, uploads each file through the existing endpoint, reports each file's status, and continues if one file fails. Uploaded files are stored locally under `backend/storage/documents` by default, while metadata is stored in PostgreSQL. The storage directory is ignored by Git.

The API provides:

- `POST /api/documents` — admin-only PDF upload
- `GET /api/documents` — authenticated document metadata listing
- `GET /api/documents/{document_id}/download` — authenticated PDF download
- `DELETE /api/documents/{document_id}` — admin-only deletion
- `GET /api/documents/search?q=...` — authenticated semantic search with snippets, pages, and similarity scores
- `POST /api/rag/ask` — authenticated question answering for both admin and employee users
- `POST /api/documents/index` — admin-only indexing of older/unindexed documents
- `POST /api/documents/{document_id}/index` — admin-only retry/re-index of one document

Uploads preserve the original filename as metadata, reject non-PDF content, enforce a 10 MB default limit, and reject identical PDF bytes with HTTP 409 using SHA-256 content comparison. Same filenames with different content are allowed; same content with different filenames is rejected. Successful and duplicate files are not retried from the same frontend selection, while genuinely failed files remain retryable. After a new document record is committed, the API marks it `indexing` and schedules local processing automatically; the background worker extracts text with `pypdf`, splits it into overlapping word chunks, and embeds it with `all-MiniLM-L6-v2` (384 dimensions). The first indexing run downloads that model into the normal local Hugging Face cache; no paid API or API key is used. Processing status is `pending`, `indexing`, `indexed`, or `failed`; processing failure does not remove the uploaded document. The React app refreshes pending/indexing documents until a terminal state is reached. In the portal, Enter submits Semantic Search and Ask AI; Shift+Enter creates a newline in Ask AI, and submissions are suppressed while text is being composed with an IME or while the same operation is already running.

Deleting a document cascades to its chunks and embeddings. Empty, image-only, corrupt, or unreadable PDFs are retained with `processing_status=failed`. Re-indexing builds embeddings before replacing existing chunks, so a successful existing index remains intact if a retry fails.

Search returns at most five results, filters out scores below `0.35`, and suppresses highly overlapping chunks from the same document page. Similarity is cosine similarity in the range 0–1, where 1 means the normalized query and chunk embeddings are identical; the score is a relevance signal, not a probability.

## Ask AI / RAG setup

The Ask AI endpoint retrieves up to five indexed chunks using the same local embedding model and exact pgvector cosine search as the search endpoint. It sends only those excerpts to the selected provider and returns an answer plus source IDs, document IDs, filenames, page numbers, similarity scores, and a `cited` flag. A source is marked `cited: true` when the answer explicitly includes an individual reference such as `[source-3]` or a grouped reference such as `[source-2, source-3]`; retrieved context without an explicit reference remains `cited: false`. Retrieved text is delimited as untrusted reference data; the model is instructed not to follow instructions inside it or invent unsupported facts. With no relevant context, the endpoint returns a clear insufficient-context answer and an empty source list without calling an LLM.

Copy `backend/.env.example` to `backend/.env` (or export the same variables) and configure one provider. Cohere is the default:

```bash
LLM_PROVIDER=cohere
COHERE_API_KEY=your-key
COHERE_MODEL=command-a-plus-05-2026
```

To switch providers without changing code, use Gemini instead:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

The model values are documented live defaults and can be changed with the provider-specific variables. API keys belong only in an ignored local `.env` or the process environment; never put them in frontend variables, source code, database records, logs, or Git. `RAG_RETRIEVAL_LIMIT` (1–10, default 5) and `RAG_MIN_SIMILARITY` (default 0.35) can tune retrieval.

Expected response:

```json
{
  "answer": "...",
  "sources": [
    {"source_id": "source-1", "document_id": 12, "filename": "handbook.pdf", "page_number": 7, "similarity": 0.91, "cited": true}
  ]
}
```

## User and role instructions

- Admins can upload one or more PDFs, monitor indexing status, download documents, retry failed indexing, and delete documents.
- Admins can use the styled PDF picker to review selected filenames before uploading, select visible documents with checkboxes, and delete selected documents after confirmation. Bulk deletion uses the existing per-document delete API and reports partial failures.
- The document list can be filtered by filename and sorted by newest or filename. These controls affect only the displayed list, not Semantic Search.
- Employees can list and download documents, use Semantic Search, and use Ask AI. They cannot upload, retry indexing, or delete documents.
- PDFs must remain within the existing 10 MB per-file limit. Uploaded documents are retained when indexing fails so an admin can retry them.
- An expired or invalid session shows a re-login message and clears account-specific state. Temporary backend or provider connectivity errors do not log the user out.
- Ask AI source entries marked `Retrieved` are relevant context returned by retrieval, not proof that the generated answer used them. Entries marked `Cited` correspond to explicit `[source-N]` references in the answer.
- Ask AI source entries can be opened through the authorized download endpoint; when a page number is available, the frontend requests the PDF and opens a temporary browser blob URL with a page fragment. Browser PDF viewers may not honor page fragments uniformly.
- Duplicate detection scans existing stored PDFs on each upload, which is suitable for the current small local dataset. It does not automatically remove duplicate records that already exist.

## Demonstration walkthrough

1. Sign in as an admin using a locally created admin user.
2. Choose one or more public or fictional PDF files, review the filenames, and click `Upload files`.
3. Wait for each document to show `Indexed and searchable`; failed documents remain available for retry.
4. Use Semantic Search with a natural-language topic or phrase and inspect the document, page, snippet, and similarity score.
5. Ask AI the same or a broader question. Review the provider/model display, answer, and source entries. `Cited` entries have explicit `[source-N]` references; `Retrieved` entries were context candidates without an explicit citation.
6. Open a source document from Ask AI or download it from the document list. Access remains authenticated.
7. Sign out and sign in as an employee. Employees can read, search, and ask questions but cannot upload, retry indexing, or delete documents.

Only send public or fictional demonstration documents to Cohere or Gemini. Do not send confidential, private, regulated, or otherwise sensitive enterprise content to an external LLM provider.

## Troubleshooting

- **Backend health is unavailable:** confirm PostgreSQL is running with `docker compose ps`, confirm `DATABASE_URL` in `backend/.env`, and check `http://127.0.0.1:8000/api/health`.
- **Migration or pgvector errors:** run `docker compose up -d postgres`, then from `backend/` run `alembic upgrade head`. Do not remove the database volume.
- **Model download or indexing errors:** the first indexing operation downloads `all-MiniLM-L6-v2` into the normal local Hugging Face cache. Ensure the backend has network access during that first run, then retry failed documents from the admin UI.
- **Ask AI configuration errors:** set `LLM_PROVIDER` to `cohere` or `gemini` and provide only the matching API key (`COHERE_API_KEY` or `GEMINI_API_KEY`) in `backend/.env`. Restart the backend after changing provider settings.
- **Frontend cannot reach the API:** start the backend on port 8000 before Vite, or update the frontend proxy/environment configuration without placing provider keys in frontend variables.

## Test and build checks

From the repository root:

```bash
cd backend
source .venv/bin/activate
python -m pytest tests
cd ../frontend
npm ci
npm test
npm run build
```

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

## Current limitations and scope

This iteration includes the React frontend, backend health endpoint, development proxy, local PostgreSQL/pgvector foundation, SQLAlchemy User, Document, and DocumentChunk models, Alembic migrations, JWT authentication, admin/employee RBAC, local PDF document management, PDF extraction, local embeddings, exact cosine semantic search, provider-selectable RAG answers, source attribution, and a non-persistent Ask AI interface. The system is PDF-only, has no persistent conversation or search history, and is intended for local development rather than deployment. Very short acronyms or ambiguous short queries may produce weaker semantic matches than descriptive phrases. Conversation history, deployment, and bulk downloads remain out of scope.
