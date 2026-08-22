"""T2AG/reading-system bridge V1 contract helpers."""

from .validator import (  # noqa: F401
    ContractError,
    canonical_json_bytes,
    load_json_strict,
    semantic_sha256,
    validate_document,
)
