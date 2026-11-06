"""Hybrid search: one Qdrant collection with dense and BM25 vectors, an exact identifier
field, metadata filters, reranking and an incremental-indexing manifest."""

import os

# Set before qdrant_client or fastembed import huggingface_hub: on Windows the model cache
# cannot use symlinks and the hub warns about it on every download.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
