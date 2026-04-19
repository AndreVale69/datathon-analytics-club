FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && uv pip install --system . pytest

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app ./app
COPY apps_sdk ./apps_sdk
COPY raw_data ./raw_data
COPY README.md ./

ENV LISTINGS_RAW_DATA_DIR=/app/raw_data
ENV LISTINGS_DB_PATH=/data/listings.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
