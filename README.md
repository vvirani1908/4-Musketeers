# AI-Powered Enterprise Knowledge Portal

CMPE 272 team project by 4-Musketeers. This repository currently contains a minimal full-stack foundation for the portal. AI processing, document management, semantic search, RAG-based question answering, authentication, and database integration will be added in later iterations.

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
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer and npm

## Local setup

From the repository root, create and activate a backend virtual environment, then install the Python dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the backend in that terminal:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

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

## Environment configuration

Example files are provided at the root, `backend/.env.example`, and `frontend/.env.example`. They contain no credentials. Copy values into local environment files only when needed; local `.env` files are ignored by Git.

## Current scope

This iteration intentionally includes only the frontend shell, backend health endpoint, and development proxy. PostgreSQL/pgvector, PDF processing, embeddings, semantic search, RAG, citations, authentication, and document workflows are out of scope for this foundation.
