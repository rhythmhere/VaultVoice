# VaultVoice

VaultVoice is an anonymous, no-login reporting and legal-information flow for survivors of gender-based violence in Nepal. It provides cautious AI-generated information, encrypted evidence storage, timeline organization, and referrals to support organizations.

## Architecture

- Frontend: Vite-built static application served by Nginx. Nginx proxies `/api` to the backend service.
- API: FastAPI with validation, rate limits, security headers, health checks, and OpenAPI docs.
- Database: PostgreSQL with SQLAlchemy and Alembic migrations.
- Evidence: MinIO S3-compatible storage. Evidence is AES-GCM encrypted before upload and tracked with SHA-256 hashes.
- AI: OpenRouter, configured entirely through environment variables.

## Prerequisites

- Docker Desktop with Compose v2
- An OpenRouter API key for report analysis and timeline generation

Docker is the only runtime dependency for the Compose workflow.

## Start the complete stack

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`, set `OPENROUTER_API_KEY`, and set `VAULTVOICE_ENCRYPTION_KEY`. Generate the encryption key with:

```powershell
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Then start everything:

```powershell
docker compose up --build
```

Open the application at http://localhost:5173. API documentation is at http://localhost:8000/api/docs, and the MinIO console is at http://localhost:9001.

On first startup Compose waits for PostgreSQL and MinIO, creates the configured MinIO bucket, runs `alembic upgrade head`, and seeds the curated NGO directory. These operations are idempotent and safe after restarts.

## Useful Docker commands

```powershell
# Run in the background
docker compose up --build -d

# Follow all logs
docker compose logs -f

# Follow one service
docker compose logs -f backend

# Rebuild after source or dependency changes
docker compose build --no-cache
docker compose up -d

# Stop containers but keep database and evidence
docker compose down

# Reset all application data (database and evidence)
docker compose down -v
```

The named volumes `postgres_data` and `minio_data` persist data across normal restarts. `docker compose down -v` permanently removes those local volumes.

## Environment configuration

`.env.example` is the single environment template for the entire repository. Copy it to `.env` at the repository root; Docker Compose, the backend, and the Vite development server all use that root file. Keep secrets such as `OPENROUTER_API_KEY` and `VAULTVOICE_ENCRYPTION_KEY` only in the uncommitted root `.env`.

Important variables include `APP_NAME`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `VAULTVOICE_ENCRYPTION_KEY`, `DATABASE_URL`, `PORT`, the PostgreSQL credentials, the MinIO credentials and bucket, `MAX_UPLOAD_BYTES`, `RATE_LIMIT`, and the host-side ports. `BACKEND_PORT` is the backend service and published host port used by Compose; `PORT` is the equivalent backend setting for standalone execution.

The development defaults use Docker service names `postgres`, `minio`, and `backend`. Do not replace these with `localhost` for connections made from a container.

## Health checks and troubleshooting

- Frontend: `http://localhost:5173/health`
- Backend: `http://localhost:8000/health`
- PostgreSQL: Compose runs `pg_isready` inside the database container.
- MinIO: Compose checks `/minio/health/ready`.

Inspect dependency state with:

```powershell
docker compose ps
docker compose logs postgres minio minio-init backend frontend
```

If the backend is unhealthy, verify that PostgreSQL is healthy, MinIO initialization completed, and `VAULTVOICE_ENCRYPTION_KEY` is a base64 URL-safe value decoding to exactly 32 bytes. If analysis requests fail with `503`, verify `OPENROUTER_API_KEY` and the configured model. If a port is already in use, change `FRONTEND_PORT`, `BACKEND_PORT`, or `MINIO_CONSOLE_PORT` in `.env` and restart Compose.

## Local development without Docker

The existing Vite/FastAPI workflow remains available when PostgreSQL and MinIO are running locally:

```powershell
python -m pip install -r backend\requirements.txt
alembic upgrade head
python -m backend.main
npm ci
npm run dev
```

## API flow

- `POST /api/ai/analyze` analyzes a report.
- `POST /api/cases` creates a PostgreSQL-backed Case ID.
- `GET /api/cases/{case_id}` retrieves a case without an account.
- `POST /api/cases/{case_id}/clarify` records an answer and re-runs analysis.
- `POST /api/cases/{case_id}/evidence` encrypts and stores evidence, then regenerates the timeline.
- `GET /api/cases/{case_id}/evidence/{id}` decrypts and streams evidence.
- `GET /api/cases/{case_id}/matches` returns explainable organization matches.
- `PATCH /api/cases/{case_id}/status` updates `open`, `ngo_contacted`, or `resolved`.
- `GET /health` and `GET /api/health` report database and object-storage health.

## Security note

This remains a demo/hackathon system until a security audit, key management, retention controls, referral verification, HTTPS deployment, and privacy review are complete. Never use development credentials or accept real survivor data in an unsecured development deployment.
