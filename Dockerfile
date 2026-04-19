FROM python:3.12-slim

WORKDIR /app

ARG TORCH_VERSION=2.11.0

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY apps_sdk ./apps_sdk
RUN pip install --no-cache-dir uv \
    && pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        "torch==${TORCH_VERSION}" \
    && uv pip install --system . pytest

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY raw_data ./raw_data

ENV LISTINGS_RAW_DATA_DIR=/app/raw_data
ENV LISTINGS_DB_PATH=/data/listings.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
