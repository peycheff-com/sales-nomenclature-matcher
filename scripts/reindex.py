#!/usr/bin/env python3
"""CLI script to reindex the catalog (embed + update search vectors)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher.indexing.indexer import reindex_catalog


async def main(embedding_model: str | None, embedding_version: str | None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = await reindex_catalog(
        embedding_model=embedding_model,
        embedding_version=embedding_version,
    )
    print(f"Reindex complete: {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reindex catalog (embeddings + search vectors)")
    parser.add_argument("--model", help="Embedding model name", default=None)
    parser.add_argument("--version", help="Embedding version tag", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.model, args.version))
