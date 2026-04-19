"""Offline preprocessing to compute listing description embeddings.

Usage:
    python scripts/precompute_embeddings.py --data-dir raw_data --out-dir artifacts

Reads CSV files in `data-dir`, extracts `listing_id` and description text
(`object_description` first, falling back to `description`), computes
L2-normalized embeddings using `sentence-transformers/all-MiniLM-L6-v2`,
and saves them to `out-dir`.

Supports incremental mode: existing artifacts are reused for rows whose
text hash is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import argparse
import csv
import hashlib
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from app.participant.description_artifacts import save_listing_embeddings

logger = logging.getLogger(__name__)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_csv_files(data_dir: Path) -> List[Path]:
    return list(data_dir.glob("*.csv"))


def read_rows_from_csvs(paths: Iterable[Path]) -> List[Tuple[str, str]]:
    """Return [(listing_id, text)] for rows with non-empty description text."""
    rows = []
    for p in paths:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                lid = row.get("listing_id") or row.get("id")
                if lid is None:
                    continue
                txt = (row.get("object_description") or row.get("description") or "").strip()
                if not txt:
                    continue
                rows.append((str(lid), txt))
    return rows


def build_embeddings(rows: List[Tuple[str, str]], model_name: str) -> Tuple[List[Tuple[str, str]], np.ndarray]:
    model = SentenceTransformer(model_name)
    lids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=True, normalize_embeddings=True)
    return list(zip(lids, [text_hash(t) for t in texts])), embs.astype(np.float32)


def incremental_update(
    existing_index_path: Path,
    existing_emb_path: Path,
    new_rows: List[Tuple[str, str]],
    new_embs: np.ndarray,
) -> Tuple[List[Tuple[str, str]], np.ndarray]:
    """Merge existing artifacts with newly computed ones, skipping unchanged rows."""
    existing_map: Dict[str, Tuple[int, str]] = {}
    existing_rows: List[Tuple[str, str]] = []
    if existing_index_path.exists() and existing_emb_path.exists():
        with existing_index_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                lid = row.get("listing_id")
                idx = int(row.get("row", "-1"))
                th = row.get("text_hash")
                if lid is None:
                    continue
                existing_map[str(lid)] = (idx, th)
                existing_rows.append((lid, th))
        existing_embs = np.load(existing_emb_path)
    else:
        existing_embs = np.zeros((0, 384), dtype=np.float32)

    to_add_rows: List[Tuple[str, str]] = []
    to_add_embs: List[np.ndarray] = []
    for (lid, th), emb in zip(new_rows, new_embs):
        prev = existing_map.get(lid)
        if prev is not None and prev[1] == th:
            continue
        to_add_rows.append((lid, th))
        to_add_embs.append(emb)

    if to_add_embs:
        to_add_matrix = np.vstack(to_add_embs).astype(np.float32)
        merged = np.vstack([existing_embs, to_add_matrix]) if existing_embs.size else to_add_matrix
        merged_rows = existing_rows + to_add_rows
    else:
        merged = existing_embs
        merged_rows = existing_rows

    return merged_rows, merged


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="raw_data")
    parser.add_argument("--out-dir", default="artifacts")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    csvs = find_csv_files(data_dir)
    if not csvs:
        logger.error("No CSV files found in %s", data_dir)
        return 2

    rows = read_rows_from_csvs(csvs)
    if not rows:
        logger.error("No descriptions found in CSVs under %s", data_dir)
        return 2

    logger.info("Found %d rows with non-empty descriptions", len(rows))

    listing_rows, listing_embs = build_embeddings(rows, args.model)

    index_path = out_dir / "listing_description_index.csv"
    emb_path = out_dir / "listing_description_embeddings.npy"
    if args.incremental:
        listing_rows, listing_embs = incremental_update(index_path, emb_path, listing_rows, listing_embs)

    save_listing_embeddings(listing_rows, listing_embs, out_dir)
    logger.info("Wrote %d listing embeddings to %s", len(listing_rows), out_dir)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
