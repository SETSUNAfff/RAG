from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the shared embedding model once per process."""
    load_dotenv(override=True)
    model_path = os.getenv("EMBEDDING_MODEL_PATH")
    if not model_path:
        raise ValueError("缺少 EMBEDDING_MODEL_PATH 配置")
    return SentenceTransformer(model_path)
