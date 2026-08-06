"""Shared deterministic fixtures for migration and release-shadow tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def write_test_authorization(
    plan_path: Path,
    result: dict,
    directory: Path,
) -> tuple[Path, str]:
    """Bind one test-only authorization receipt to an immutable migration plan."""
    plan = json.loads(plan_path.read_bytes().decode("utf-8"))
    approval = f"TEST E {plan['plan_id']} {result['file_sha256']}"
    payload = {
        "campaign_id": plan["campaign_id"],
        "phase": "E_AUTHORIZED",
        "state": "test_authorized",
        "authorization_mode": "test",
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "plan_file_sha256": result["file_sha256"],
        "payload_sha256": result["payload_sha256"],
        "d_review_sha256": "1" * 64,
        "executor_bundle_sha256": plan["executor_bundle_sha256"],
        "baseline_binding_sha256": plan["baseline_binding_sha256"],
        "worktree_manifest_sha256": plan["worktree_manifest_sha256"],
        "watched_root_manifest_sha256": plan["watched_root_manifest"]["sha256"],
        "approval_text": approval,
        "approval_text_sha256": hashlib.sha256(approval.encode()).hexdigest(),
        "authorization_source_sha256": "2" * 64,
    }
    path = directory / "test-authorization.json"
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()
