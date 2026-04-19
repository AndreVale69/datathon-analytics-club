# Datathon Analytics Club

> **Security warning:** The API is currently configured with `allow_origins=["*"]` (open CORS) and has no authentication. This is intentional for local development and demo purposes only. Do **not** deploy this configuration to production — restrict CORS to specific origins and add authentication before any public-facing deployment.

This repository is a starter implementation for the Datathon 2026 real-estate search challenge: parse a natural-language housing query, apply hard constraints, and rank valid listings by soft relevance.

The repo contains:

- a FastAPI backend in `app/`
- a minimal MCP / Apps SDK server in `apps_sdk/server/`
- a Vite + React widget in `apps_sdk/web/`
- tests for the API, bootstrap flow, and MCP metadata

## Table Of Contents

- [AWS Side Challenge](#aws-side-challenge)
- [What The Challenge Asks For](#what-the-challenge-asks-for)
- [Current Repo Status](#current-repo-status)
- [Local Secrets And Env Files](#local-secrets-and-env-files)
- [Hackathon-Available Bedrock Models](#hackathon-available-bedrock-models)
- [GitHub Secrets](#github-secrets)
- [Requirements](#requirements)
- [Quick Start](#quick-start)

## AWS Side Challenge

This project is also submitted for the AWS side challenge.

AWS usage in this project:

- Amazon Bedrock for LLM-based query understanding, including extraction of hard constraints and soft preferences from natural-language apartment searches.
- Amazon S3 for apartment image storage and retrieval in the application pipeline.
- Separate AWS credential paths for S3 image access and Bedrock model access, so the image pipeline and the LLM pipeline can be configured independently.

Current Bedrock setup used in this repo:

- Working Bedrock model for this workshop account: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- The app now chooses providers and models per extraction stage through env vars instead of one global provider toggle.

Hackathon model reference:

- See [Hackathon-available Bedrock models](#hackathon-available-bedrock-models) below for the full list of models allowed in this event.

Security note:

- Do not create S3 buckets with unrestricted public access. Restrict access using S3 Block Public Access and/or a restrictive bucket policy.

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

See [raw_data/README.md](raw_data/README.md) for the expected data setup.

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

- `OPENAI_API_KEY`
- `HARD_CONSTRAINTS_PROVIDER`
- `HARD_CONSTRAINTS_OPENAI_MODEL`
- `HARD_CONSTRAINTS_BEDROCK_MODEL_ID`
- `SOFT_PREFERENCES_PROVIDER`
- `SOFT_PREFERENCES_OPENAI_MODEL`
- `SOFT_PREFERENCES_BEDROCK_MODEL_ID`
- `GEOLOCATION_PROVIDER`
- `GEOLOCATION_OPENAI_MODEL`
- `GEOLOCATION_BEDROCK_MODEL_ID`
- `EXPLANATION_PROVIDER`
- `EXPLANATION_OPENAI_MODEL`
- `EXPLANATION_BEDROCK_MODEL_ID`
- `BEDROCK_AWS_REGION`
- `BEDROCK_AWS_ACCESS_KEY_ID`
- `BEDROCK_AWS_SECRET_ACCESS_KEY`
- `BEDROCK_AWS_SESSION_TOKEN`
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
OPENAI_API_KEY=

HARD_CONSTRAINTS_PROVIDER=openai
HARD_CONSTRAINTS_OPENAI_MODEL=gpt-5-mini
HARD_CONSTRAINTS_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0

SOFT_PREFERENCES_PROVIDER=openai
SOFT_PREFERENCES_OPENAI_MODEL=gpt-5-mini
SOFT_PREFERENCES_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0

GEOLOCATION_PROVIDER=openai
GEOLOCATION_OPENAI_MODEL=gpt-5-mini
GEOLOCATION_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0

EXPLANATION_PROVIDER=bedrock
EXPLANATION_OPENAI_MODEL=gpt-5-mini
EXPLANATION_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0

BEDROCK_AWS_REGION=
BEDROCK_AWS_ACCESS_KEY_ID=
BEDROCK_AWS_SECRET_ACCESS_KEY=
BEDROCK_AWS_SESSION_TOKEN=

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

Stage defaults:

- Hard constraints: `openai` with `gpt-5-mini`
- Soft preferences: `openai` with `gpt-5-mini`
- Geolocation intent: `openai` with `gpt-5-mini`
- Explanation generation: `bedrock` with `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- For any stage set to `bedrock`, the stage uses its `*_BEDROCK_MODEL_ID` together with `BEDROCK_AWS_*` credentials or the standard AWS credential chain
- `BEDROCK_AWS_REGION` is optional; if empty, the app falls back to `AWS_REGION` or `AWS_DEFAULT_REGION`
- See [Hackathon-Available Bedrock Models](#hackathon-available-bedrock-models) for the full list of models allowed in this event and the Bedrock IDs used in this repo.

### Choose Providers And Models Per Stage

Default extraction setup recommended for ranking quality:

```dotenv
OPENAI_API_KEY=your_openai_key

HARD_CONSTRAINTS_PROVIDER=openai
HARD_CONSTRAINTS_OPENAI_MODEL=gpt-5-mini

SOFT_PREFERENCES_PROVIDER=openai
SOFT_PREFERENCES_OPENAI_MODEL=gpt-5-mini

GEOLOCATION_PROVIDER=openai
GEOLOCATION_OPENAI_MODEL=gpt-5-mini

EXPLANATION_PROVIDER=bedrock
EXPLANATION_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
```

If you want to use Bedrock for one specific stage, change only that stage:

```dotenv
HARD_CONSTRAINTS_PROVIDER=bedrock
HARD_CONSTRAINTS_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_AWS_REGION=us-west-2

AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_DEFAULT_REGION=us-west-2
```

Notes:

- Each stage is configured independently.
- When a stage uses `openai`, that stage ignores its Bedrock model ID.
- When a stage uses `bedrock`, that stage ignores its OpenAI model setting.
- If you are inside the AWS workshop environment, credentials may already be injected into the shell or attached role, so you might only need to set the stage provider and its Bedrock model ID.
- The frontend `Explain me why` action calls the explanation stage only on demand, so you do not pay an explanation-model call for every search result.

If you need one AWS credential set for S3 images and a different one for Bedrock, keep the image credentials in the standard AWS variables and put the Bedrock credentials in the dedicated Bedrock variables:

```dotenv
HARD_CONSTRAINTS_PROVIDER=bedrock

AWS_ACCESS_KEY_ID=images_key
AWS_SECRET_ACCESS_KEY=images_secret
AWS_SESSION_TOKEN=images_session_token
AWS_DEFAULT_REGION=us-west-2

HARD_CONSTRAINTS_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_AWS_REGION=us-west-2
BEDROCK_AWS_ACCESS_KEY_ID=bedrock_key
BEDROCK_AWS_SECRET_ACCESS_KEY=bedrock_secret
BEDROCK_AWS_SESSION_TOKEN=bedrock_session_token
```

In that setup:

- S3 image access uses `AWS_*`
- Bedrock uses `BEDROCK_AWS_*`

Recommended hybrid setup for this repo:

- `HARD_CONSTRAINTS_PROVIDER=openai`
- `SOFT_PREFERENCES_PROVIDER=openai`
- `GEOLOCATION_PROVIDER=openai`
- `EXPLANATION_PROVIDER=bedrock`
- switch an individual extraction stage to `bedrock` only if it performs better in your evaluation queries

## Hackathon-Available Bedrock Models

The organizers stated that the following models are available for the hackathon:

- All Amazon models
  Recommended text models for this repo:
  `us.amazon.nova-micro-v1:0`, `us.amazon.nova-lite-v1:0`
- Anthropic Claude Sonnet 4.5
  In-Region model ID: `anthropic.claude-sonnet-4-5-20250929-v1:0`
  US inference profile: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
  EU inference profile: `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`
- Anthropic Claude Opus 4.5
  In-Region model ID: `anthropic.claude-opus-4-5-20251101-v1:0`
  US inference profile: `us.anthropic.claude-opus-4-5-20251101-v1:0`
  EU inference profile: `eu.anthropic.claude-opus-4-5-20251101-v1:0`
- Meta Llama 4 Maverick 17B Instruct
  In-Region model ID: `meta.llama4-maverick-17b-instruct-v1:0`
  US inference profile: `us.meta.llama4-maverick-17b-instruct-v1:0`
- Mistral Pixtral Large (25.02)
  In-Region model ID: `mistral.pixtral-large-2502-v1:0`
  US inference profile: `us.mistral.pixtral-large-2502-v1:0`
  EU inference profile: `eu.mistral.pixtral-large-2502-v1:0`
- Stable Diffusion 3.5 Large
  Model ID: `stability.sd3-5-large-v1:0`

Notes:

- Some Bedrock models require an inference profile instead of direct on-demand invocation. In this hackathon setup, `us.anthropic.claude-sonnet-4-5-20250929-v1:0` worked, while the plain Sonnet 4.5 model ID did not.
- Actual runtime access still depends on the permissions attached to the workshop AWS role. A model can be listed as available for the hackathon and still be blocked for a specific participant role by IAM policy.

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

## Quick Start

The recommended first way to run the project is with Docker Compose.

### 1. Create local env files

```bash
cp .env.example .env.local
```

### 2. Add the dataset

Download the dataset from the shared source and extract or copy its contents into `raw_data/` in the repo root.

Do not commit the dataset itself to Git. Keep only the code and documentation in the repository.

Detailed instructions are in [raw_data/README.md](raw_data/README.md).

### 3. Run with Docker Compose first

If you prefer Docker, you do not need to create a Python virtual environment locally.

Before building the containers, make sure `raw_data/` already contains the dataset. The `Dockerfile` copies that directory into the image, so the build will fail if it is missing.

```bash
docker compose up --build
```

This starts:

- API on `http://localhost:8000`
- MCP server on `http://localhost:8001/mcp`

Important:

- `http://localhost:8000` is the backend API
- `http://localhost:8001/mcp` is the MCP endpoint
- `http://localhost:8001` is not a normal standalone frontend webpage

Useful checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/mcp
```

The frontend widget on port `8001` is meant to be loaded by an MCP-compatible host, not used as a normal browser app page.

To run the test suite in Docker:

```bash
docker compose run --rm tests
```

### 4. To see the frontend in a browser

If you want to see the React frontend as a normal webpage, run the Vite dev server separately:

```bash
cd apps_sdk/web
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

If you want to preview the production build instead:

```bash
cd apps_sdk/web
npm install
npm run build
npm run preview
```

Then open the preview URL printed by Vite, usually:

```text
http://localhost:4173
```

### 5. Local Python setup with `uv`

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

### 6. Local Python setup without `uv`

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

### 7. Run the widget and MCP server with local Python

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

## Useful Commands

Run tests locally with `uv`:

```bash
uv run pytest
```

Run tests with Docker Compose:

```bash
docker compose run --rm tests
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
