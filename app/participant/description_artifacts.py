from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Tuple
import csv
import logging

import numpy as np

logger = logging.getLogger(__name__)


def load_listing_embeddings(artifacts_dir: Path | str = "artifacts") -> Tuple[Dict[str, int], np.ndarray, Dict[str, str]] | None:
    """Load precomputed listing embeddings and index.

    Returns (listing_id_to_row, embeddings, listing_id_to_hash) or None if missing.
    """
    artifacts_dir = Path(artifacts_dir)
    emb_path = artifacts_dir / "listing_description_embeddings.npy"
    index_path = artifacts_dir / "listing_description_index.csv"
    if not emb_path.exists() or not index_path.exists():
        logger.debug("Listing embeddings missing at %s", artifacts_dir)
        return None
    try:
        embs = np.load(emb_path)
        listing_to_row: Dict[str, int] = {}
        listing_to_hash: Dict[str, str] = {}
        with index_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                lid = row.get("listing_id")
                idx = int(row.get("row", "-1"))
                th = row.get("text_hash")
                if lid is not None and idx >= 0:
                    listing_to_row[lid] = idx
                    listing_to_hash[lid] = th
        return listing_to_row, embs, listing_to_hash
    except Exception:
        logger.exception("Failed to load listing embeddings from %s", artifacts_dir)
        return None


def save_listing_embeddings(listing_rows: Iterable[Tuple[str, str]], embeddings: Any, artifacts_dir: Path | str = "artifacts") -> None:
    """Save listing embeddings.

    listing_rows: iterable of (listing_id, text_hash) in the same order as embeddings rows.
    """
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    emb_path = artifacts_dir / "listing_description_embeddings.npy"
    index_path = artifacts_dir / "listing_description_index.csv"
    np.save(emb_path, embeddings)
    # write index with row ordering
    with index_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["row", "listing_id", "text_hash"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for i, (lid, th) in enumerate(listing_rows):
            writer.writerow({"row": i, "listing_id": lid, "text_hash": th})
