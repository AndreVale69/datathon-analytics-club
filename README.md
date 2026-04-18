# Datathon Analytics Club

This repository is a starter implementation for the Datathon 2026 real-estate search challenge: parse a natural-language housing query, apply hard constraints, and rank valid listings by soft relevance.

The repo contains:

- a FastAPI backend in `app/`
- a minimal MCP / Apps SDK server in `apps_sdk/server/`
- a Vite + React widget in `apps_sdk/web/`
- tests for the API, bootstrap flow, and MCP metadata

## What The Challenge Asks For

Based on the challenge brief and portal material, the expected prototype should:

- accept a natural-language real-estate query
- extract hard filters such as city, rooms, and budget
- return only listings that satisfy those hard constraints
- rank the remaining listings by softer preferences such as brightness, commute, modernity, or parking
- be reachable through a public HTTPS endpoint for the final demo/submission

The main judging focus is ranking quality and hard-constraint correctness. The MCP app and widget are optional support tooling, not the core deliverable.

## Current Repo Status

This checkout includes a placeholder `raw_data/` directory, but the actual challenge dataset is not committed to Git. The API will not bootstrap correctly until you download the dataset from the shared source and place it into `raw_data/`.

Expected layout:

```text
datathon-analytics-club/
  raw_data/
    ...
```

See [raw_data/README.md](/home/andre/university/datathon-analytics-club/raw_data/README.md) for the expected data setup.

## Local Secrets And Env Files

Local configuration is now read automatically from:

1. `.env.local`
2. `.env`
3. exported shell variables

`.env.local` is gitignored, so it is not pushed to GitHub and is safe for machine-specific values and secrets. `.env.example` is tracked and documents the variables the project understands.

Files:

- `.env.example`: committed reference
- `.env.local`: local-only file, already created and ignored by Git, so it will not be pushed

Important variables:

- `LISTINGS_RAW_DATA_DIR`: location of the extracted challenge data
- `LISTINGS_DB_PATH`: SQLite database path used by the API bootstrap
- `LISTINGS_S3_BUCKET`
- `LISTINGS_S3_REGION`
- `LISTINGS_S3_PREFIX`
- `APPS_SDK_LISTINGS_API_BASE_URL`: where the MCP server reaches the FastAPI API
- `APPS_SDK_PUBLIC_BASE_URL`: public base URL used to generate widget asset URLs
- `APPS_SDK_PORT`
- `MCP_ALLOWED_HOSTS`
- `MCP_ALLOWED_ORIGINS`

Recommended local setup:

```bash
cp .env.example .env.local
```

Then edit `.env.local` and set the values you want to use locally:

```dotenv
LISTINGS_RAW_DATA_DIR=raw_data
LISTINGS_DB_PATH=data/listings.db

LISTINGS_S3_BUCKET=
LISTINGS_S3_REGION=eu-central-2
LISTINGS_S3_PREFIX=prod

APPS_SDK_LISTINGS_API_BASE_URL=http://localhost:8000
APPS_SDK_PUBLIC_BASE_URL=http://localhost:8001
APPS_SDK_PORT=8001

MCP_ALLOWED_HOSTS=
MCP_ALLOWED_ORIGINS=
```

Leave `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` empty for normal local development. Only set them when you have a real public host and want stricter request validation.

If you want to confirm Git will ignore the file:

```bash
git status --ignored .env.local
```

## GitHub Secrets

GitHub Secrets are optional for local development. Use them only if you later add GitHub Actions or deploy from GitHub.

If a workflow or deployment needs AWS credentials, you mentioned these are available in GitHub Secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`

You can also add repo-level secrets for project-specific values if needed, for example:

- `LISTINGS_S3_BUCKET`
- `LISTINGS_S3_REGION`
- `LISTINGS_S3_PREFIX`
- `APPS_SDK_PUBLIC_BASE_URL`

Recommended split:

- local development: keep values in `.env.local`
- GitHub Actions or deployment: keep values in GitHub Secrets
- committed documentation: keep placeholders only in `.env.example`

## Quick Start

## Requirements

You have two supported ways to run the project:

- Docker-first: easiest if you do not want to manage a local Python environment
- local Python: use `uv` or a standard virtual environment

Minimum tools:

- Python `3.12`
- Node.js and `npm` for `apps_sdk/web`
- Docker and Docker Compose if you want the containerized setup

Note: both the local and Docker flows require `raw_data/` to exist first.

### Install `uv`

`uv` is a standalone developer tool. Install it at user level on your machine, not inside the project virtual environment. The reason is simple: `uv` is the tool that creates and manages the environment, so it should exist before the project env does.

If `uv` is not installed, use one of these:

```bash
pip install uv
```

or:

```bash
pipx install uv
```

or on macOS with Homebrew:

```bash
brew install uv
```

Check that it is available:

```bash
uv --version
```

If you do not want to install `uv` as a user-level tool, skip it and use the plain `venv` flow documented below.

### 1. Create local env files

```bash
cp .env.example .env.local
```

### 2. Add the dataset

Download the dataset from the shared source and extract or copy its contents into `raw_data/` in the repo root.

Do not commit the dataset itself to Git. Keep only the code and documentation in the repository.

Detailed instructions are in [raw_data/README.md](/home/andre/university/datathon-analytics-club/raw_data/README.md).

### 3. Local Python setup with `uv`

Install backend dependencies:

```bash
uv sync --dev
```

Run the API:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Available at `http://localhost:8000`.

Useful check:

```bash
curl http://localhost:8000/health
```

The SQLite database is created automatically from the CSV data on startup.

### 4. Local Python setup without `uv`

If `uv` does not work on your machine, create a normal virtual environment instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
pip install pytest
```

Then run the API with:

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Run the widget and MCP server

Build the frontend once:

```bash
cd apps_sdk/web
npm install
npm run build
```

Start the MCP server from the repo root:

```bash
uv run uvicorn apps_sdk.server.main:app --reload --port 8001
```

If you are using the plain virtualenv fallback instead of `uv`, run:

```bash
uvicorn apps_sdk.server.main:app --reload --port 8001
```

MCP endpoint:

```text
http://localhost:8001/mcp
```

## Run With Docker

If you prefer Docker, you do not need to create a Python virtual environment locally.

Before building the containers, make sure `raw_data/` already exists in the repo root. The `Dockerfile` copies that directory into the image, so the build will fail if it is missing.

```bash
docker compose up --build
```

This starts:

- API on `http://localhost:8000`
- MCP server on `http://localhost:8001/mcp`

The compose setup mounts the repository into the containers, so the same `.env.local` file can be used there too.

## Useful Commands

Run tests:

```bash
uv run pytest
```

Run the MCP smoke test after building the widget and starting the MCP server:

```bash
uv run python scripts/mcp_smoke.py --url http://localhost:8001/mcp
```

## Where To Implement Your Logic

Most participant-facing code lives in `app/participant/`:

- `hard_fact_extraction.py`
- `soft_fact_extraction.py`
- `soft_filtering.py`
- `ranking.py`
- `listing_row_parser.py`

Harness/bootstrap code lives in `app/harness/`:

- `bootstrap.py`
- `csv_import.py`
- `search_service.py`

## Public Demo / Submission Note

The challenge deliverable expects a publicly reachable HTTPS route. For MCP testing with a tunnel, set:

```dotenv
APPS_SDK_PUBLIC_BASE_URL=https://your-public-host
APPS_SDK_LISTINGS_API_BASE_URL=http://localhost:8000
```

Then restart the MCP server so it rebuilds widget URLs with the public origin.
