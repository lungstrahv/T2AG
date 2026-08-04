#!/usr/bin/env python3
"""Run the 0.2.1 reading-bridge LOOP saga in two isolated physical roots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


TOOLS = Path(__file__).resolve().parent
DEFAULT_T2AG_SCRIPT = TOOLS / "t2ag_reading_bridge.py"
DEFAULT_CONTRACTS = TOOLS / "contracts" / "reading_bridge_v1"


class SagaError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(script: Path, root: Path, *arguments: str) -> Any:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--root", str(root), *arguments],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise SagaError(
            f"command failed ({result.returncode}): {script.name} {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SagaError(f"command did not return JSON: {result.stdout!r}") from error


def run_ok(script: Path, root: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--root", str(root), *arguments],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise SagaError(
            f"command failed ({result.returncode}): {script.name} {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def run_fail(
    script: Path,
    root: Path,
    *arguments: str,
    environment_override: dict[str, str] | None = None,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if environment_override:
        environment.update(environment_override)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--root", str(root), *arguments],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode == 0:
        raise SagaError(f"negative command unexpectedly passed: {script.name} {' '.join(arguments)}")


def manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def manifest_sha(value: dict[str, str]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def record_transition(
    transitions: list[dict[str, Any]],
    name: str,
    before_t2ag: dict[str, str],
    before_reading: dict[str, str],
    after_t2ag: dict[str, str],
    after_reading: dict[str, str],
) -> None:
    transitions.append(
        {
            "step": name,
            "t2ag": {
                "before": manifest_sha(before_t2ag),
                "after": manifest_sha(after_t2ag),
                "changed": changed_paths(before_t2ag, after_t2ag),
            },
            "reading": {
                "before": manifest_sha(before_reading),
                "after": manifest_sha(after_reading),
                "changed": changed_paths(before_reading, after_reading),
            },
        }
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SagaError(message)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_t2ag_fixture(root: Path, contracts: Path) -> None:
    shutil.copytree(contracts, root / "main/70_tools/contracts/reading_bridge_v1")
    activity = root / "main/10_student/activities/reading/AR-9001_LOOP.md"
    write_text(
        activity,
        "---\n"
        "type: activity_record\n"
        "activity_kind: reading\n"
        "activity_record_id: AR-9001\n"
        "title: Isolated bridge saga\n"
        "record_status: recording\n"
        "created_at: 2026-08-04\n"
        "---\n"
        "# Isolated bridge saga\n",
    )
    context_source = {
        "schema": "t2ag.reading_context_source.v1",
        "activity_record_id": "AR-9001",
        "target_reading_uri": "reading://book/B901",
        "course_id": "TEST1001",
        "confirmed_by": "student",
        "confirmed_at": "2026-08-04T04:00:00Z",
        "reading_intents": [
            {
                "source_id": "INTENT-LOOP-001",
                "source_path": "main/10_student/activities/reading/AR-9001_LOOP.md",
                "text": "观察证据边界如何限制结论。",
            }
        ],
        "questions_or_observation_cues": [
            {
                "source_id": "SAGA-Q001",
                "source_path": "main/10_student/activities/reading/AR-9001_LOOP.md",
                "text": "哪些证据足以支持候选判断？",
            }
        ],
    }
    write_json(activity.with_name("AR-9001.context.json"), context_source)


def prepare_recovery_case(
    case_root: Path,
    t2ag_script: Path,
    reading_script: Path,
    contracts: Path,
    receipt_id: str,
) -> dict[str, Any]:
    t2ag_root = case_root / "t2ag-fixture"
    reading_root = case_root / "reading-fixture"
    exchange = case_root / "exchange"
    prepare_t2ag_fixture(t2ag_root, contracts)
    run_ok(reading_script, reading_root, "init-book", "--id", "B901", "--title", "Recovery fixture")
    run_ok(
        reading_script,
        reading_root,
        "add-chapter",
        "--book",
        "B901",
        "--id",
        "CH01",
        "--title",
        "Recovery",
        "--start",
        "1",
        "--end",
        "2",
    )
    run_ok(
        reading_script,
        reading_root,
        "add-note",
        "--book",
        "B901",
        "--chapter",
        "CH01",
        "--page",
        "1",
        "--kind",
        "thought",
        "--quote",
        "Synthetic recovery anchor.",
        "--thought",
        "Recovery must converge from the durable local owner state.",
    )
    contribution = run_json(
        reading_script,
        reading_root,
        "t2ag-export",
        "--book",
        "B901",
        "--note",
        "B901-CH01-P0001-N01",
        "--target-activity-record-id",
        "AR-9001",
        "--event-id",
        f"EVT-{receipt_id[4:]}",
        "--generated-at",
        "2026-08-04T05:00:00Z",
        "--question",
        "Can the interrupted receipt saga converge?",
        "--supports",
        "The durable pending record provides the recovery anchor.",
    )
    contribution_file = exchange / "contribution.json"
    write_json(contribution_file, contribution)
    run_json(t2ag_script, t2ag_root, "contribution-import", "--file", str(contribution_file))
    use_relative = "main/40_course/TEST1001/lessons/lesson01/lesson01.md"
    write_text(
        t2ag_root.joinpath(*use_relative.split("/")),
        f"used candidate {contribution['contribution_id']}\n",
    )
    receipt_arguments = (
        "receipt-prepare",
        "--activity",
        "AR-9001",
        "--contribution-id",
        contribution["contribution_id"],
        "--receipt-id",
        receipt_id,
        "--consumer-uri",
        f"t2ag://path/{use_relative}",
        "--used-at",
        "2026-08-04T05:10:00Z",
        "--purpose",
        "Exercise isolated receipt recovery.",
        "--generated-at",
        "2026-08-04T05:10:00Z",
    )
    receipt = run_json(t2ag_script, t2ag_root, *receipt_arguments)
    return {
        "t2ag_root": t2ag_root,
        "reading_root": reading_root,
        "exchange": exchange,
        "receipt": receipt,
        "receipt_id": receipt_id,
    }


def finish_recovery_case(case: dict[str, Any]) -> dict[str, Any]:
    t2ag_root = case["t2ag_root"]
    reading_root = case["reading_root"]
    ledger = load_json(
        t2ag_root / "main/10_student/activities/reading/AR-9001.contributions.json"
    )
    page = reading_root / "main/10_books/B901/pages/CH01/p0001.md"
    require(len(ledger["receipt_outbox"]) == 1, "recovery outbox cardinality drifted")
    require(ledger["receipt_outbox"][0]["status"] == "acknowledged", "recovery did not acknowledge")
    require(page.read_text(encoding="utf-8").count("READING_USE_RECEIPT_V1") == 1, "recovery duplicated receipt")
    return {
        "status": "converged",
        "receipt_id": case["receipt_id"],
        "t2ag_manifest": manifest_sha(manifest(t2ag_root)),
        "reading_manifest": manifest_sha(manifest(reading_root)),
    }


def run_recovery_cases(
    root: Path,
    t2ag_script: Path,
    reading_script: Path,
    contracts: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}

    prepare_lost = prepare_recovery_case(
        root / "prepare-response-loss",
        t2ag_script,
        reading_script,
        contracts,
        "RCP-RECOVERPREP000001",
    )
    pending = run_json(
        t2ag_script,
        prepare_lost["t2ag_root"],
        "receipt-list-pending",
        "--activity",
        "AR-9001",
    )
    require(len(pending) == 1, "prepare response loss did not leave one pending receipt")
    recovered_receipt = prepare_lost["exchange"] / "recovered-pending.json"
    write_json(recovered_receipt, pending[0])
    owner = run_json(
        reading_script,
        prepare_lost["reading_root"],
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(recovered_receipt),
    )
    owner_file = prepare_lost["exchange"] / "owner.json"
    write_json(owner_file, owner)
    run_json(
        t2ag_script,
        prepare_lost["t2ag_root"],
        "receipt-ack",
        "--response-file",
        str(owner_file),
    )
    results["prepare_response_lost"] = finish_recovery_case(prepare_lost)

    owner_lost = prepare_recovery_case(
        root / "owner-response-loss",
        t2ag_script,
        reading_script,
        contracts,
        "RCP-RECOVEROWNER0001",
    )
    owner_lost_receipt = owner_lost["exchange"] / "receipt.json"
    write_json(owner_lost_receipt, owner_lost["receipt"])
    run_fail(
        reading_script,
        owner_lost["reading_root"],
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(owner_lost_receipt),
        environment_override={"READING_BRIDGE_TEST_FAULT": "after_replace"},
    )
    recovered_owner = run_json(
        reading_script,
        owner_lost["reading_root"],
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(owner_lost_receipt),
    )
    require(recovered_owner["result"] == "already_applied", "owner response loss did not replay")
    recovered_owner_file = owner_lost["exchange"] / "owner-recovered.json"
    write_json(recovered_owner_file, recovered_owner)
    run_json(
        t2ag_script,
        owner_lost["t2ag_root"],
        "receipt-ack",
        "--response-file",
        str(recovered_owner_file),
    )
    results["owner_response_lost"] = finish_recovery_case(owner_lost)

    ack_late = prepare_recovery_case(
        root / "ack-before-interruption",
        t2ag_script,
        reading_script,
        contracts,
        "RCP-RECOVERACK0000001",
    )
    ack_late_receipt = ack_late["exchange"] / "receipt.json"
    write_json(ack_late_receipt, ack_late["receipt"])
    saved_owner = run_json(
        reading_script,
        ack_late["reading_root"],
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(ack_late_receipt),
    )
    pending_before_late_ack = run_json(
        t2ag_script,
        ack_late["t2ag_root"],
        "receipt-list-pending",
        "--activity",
        "AR-9001",
    )
    require(len(pending_before_late_ack) == 1, "pre-ack interruption did not preserve pending")
    saved_owner_file = ack_late["exchange"] / "owner-saved.json"
    write_json(saved_owner_file, saved_owner)
    run_json(
        t2ag_script,
        ack_late["t2ag_root"],
        "receipt-ack",
        "--response-file",
        str(saved_owner_file),
    )
    results["ack_before_interruption"] = finish_recovery_case(ack_late)
    return results


def run_saga(
    fixture: Path,
    t2ag_script: Path,
    reading_script: Path,
    contracts: Path,
) -> dict[str, Any]:
    t2ag_root = fixture / "t2ag-fixture"
    reading_root = fixture / "reading-fixture"
    require(t2ag_root != reading_root, "fixture roots must be physically distinct")
    prepare_t2ag_fixture(t2ag_root, contracts)

    run_ok(reading_script, reading_root, "init-book", "--id", "B901", "--title", "Bridge saga book")
    run_ok(
        reading_script,
        reading_root,
        "add-chapter",
        "--book",
        "B901",
        "--id",
        "CH01",
        "--title",
        "Boundary",
        "--start",
        "1",
        "--end",
        "10",
    )
    run_ok(
        reading_script,
        reading_root,
        "add-note",
        "--book",
        "B901",
        "--chapter",
        "CH01",
        "--page",
        "1",
        "--kind",
        "question",
        "--quote",
        "A short synthetic source anchor.",
        "--thought",
        "The candidate must remain traceable to this isolated note.",
    )
    note_id = "B901-CH01-P0001-N01"
    run_ok(
        reading_script,
        reading_root,
        "network-add",
        "--book",
        "B901",
        "--type",
        "concept",
        "--status",
        "candidate",
        "--provenance",
        "reader_inference",
        "--title",
        "LOOP candidate",
        "--content",
        "A bounded candidate index with a local evidence anchor.",
        "--evidence",
        note_id,
        "--cannot-prove",
        "It cannot prove that the student has mastered the topic.",
        "--next-use",
        "Use only in the isolated TEST1001 fixture.",
    )
    run_ok(reading_script, reading_root, "network-review", "--book", "B901")

    exchange = fixture / "exchange"
    transitions: list[dict[str, Any]] = []
    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    context = run_json(
        t2ag_script,
        t2ag_root,
        "context-export",
        "--activity",
        "AR-9001",
        "--event-id",
        "EVT-SAGA-CONTEXT-0001",
        "--generated-at",
        "2026-08-04T04:05:00Z",
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "context-export", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag and after_reading == before_reading, "context export wrote state")
    context_file = exchange / "context.json"
    write_json(context_file, context)
    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    context_import = run_json(
        reading_script,
        reading_root,
        "t2ag-context-import",
        "--book",
        "B901",
        "--context-file",
        str(context_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "context-import", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(changed_paths(before_t2ag, after_t2ag) == [], "context import changed T2AG")
    require(
        changed_paths(before_reading, after_reading) == ["main/10_books/B901/t2ag_context.json"],
        "context import changed an unexpected reading path",
    )
    before_t2ag = after_t2ag
    before_reading = after_reading
    context_replay = run_json(
        reading_script,
        reading_root,
        "t2ag-context-import",
        "--book",
        "B901",
        "--context-file",
        str(context_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "context-replay", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag and after_reading == before_reading, "context replay wrote state")

    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    contribution = run_json(
        reading_script,
        reading_root,
        "t2ag-export",
        "--book",
        "B901",
        "--node",
        "K-B901-0001",
        "--receipt-note",
        note_id,
        "--target-activity-record-id",
        "AR-9001",
        "--event-id",
        "EVT-SAGA-CONTRIB-0001",
        "--generated-at",
        "2026-08-04T04:10:00Z",
        "--question",
        "What does this isolated evidence support?",
        "--supports",
        "It supports a traceable candidate, not a final conclusion.",
        "--limits",
        "The note is synthetic and local to this fixture.",
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "contribution-export", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag and after_reading == before_reading, "contribution export wrote state")
    contribution_file = exchange / "contribution.json"
    write_json(contribution_file, contribution)
    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    contribution_import = run_json(
        t2ag_script,
        t2ag_root,
        "contribution-import",
        "--file",
        str(contribution_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "contribution-import", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(
        changed_paths(before_t2ag, after_t2ag)
        == ["main/10_student/activities/reading/AR-9001.contributions.json"],
        "contribution import changed an unexpected T2AG path",
    )
    require(after_reading == before_reading, "contribution import changed reading state")
    before_t2ag = after_t2ag
    before_reading = after_reading
    contribution_replay = run_json(
        t2ag_script,
        t2ag_root,
        "contribution-import",
        "--file",
        str(contribution_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "contribution-replay", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag and after_reading == before_reading, "contribution replay wrote state")

    use_relative = "main/40_course/TEST1001/lessons/lesson01/lesson01.md"
    use_path = t2ag_root.joinpath(*use_relative.split("/"))
    write_text(
        use_path,
        "# Isolated use position\n\n"
        f"Used candidate `{contribution['contribution_id']}` for a synthetic comparison.\n",
    )
    receipt_arguments = (
        "receipt-prepare",
        "--activity",
        "AR-9001",
        "--contribution-id",
        contribution["contribution_id"],
        "--receipt-id",
        "RCP-LOOP000000000001",
        "--consumer-uri",
        f"t2ag://path/{use_relative}",
        "--used-at",
        "2026-08-04T04:20:00Z",
        "--purpose",
        "Verify the isolated end-to-end reading bridge.",
        "--generated-at",
        "2026-08-04T04:20:00Z",
    )
    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    receipt = run_json(t2ag_script, t2ag_root, *receipt_arguments)
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "receipt-prepare", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(
        changed_paths(before_t2ag, after_t2ag)
        == ["main/10_student/activities/reading/AR-9001.contributions.json"],
        "receipt prepare changed an unexpected T2AG path",
    )
    require(after_reading == before_reading, "receipt prepare changed reading state")
    ledger_after_prepare = (
        t2ag_root / "main/10_student/activities/reading/AR-9001.contributions.json"
    )
    prepare_bytes = ledger_after_prepare.read_bytes()
    prepare_mtime = ledger_after_prepare.stat().st_mtime_ns
    receipt_replay = run_json(t2ag_script, t2ag_root, *receipt_arguments)
    replay_t2ag = manifest(t2ag_root)
    replay_reading = manifest(reading_root)
    record_transition(
        transitions, "receipt-prepare-replay", after_t2ag, after_reading, replay_t2ag, replay_reading
    )
    require(receipt_replay == receipt, "receipt prepare replay changed payload")
    require(ledger_after_prepare.read_bytes() == prepare_bytes, "receipt prepare replay changed bytes")
    require(ledger_after_prepare.stat().st_mtime_ns == prepare_mtime, "receipt prepare replay changed mtime")
    receipt_file = exchange / "receipt.json"
    write_json(receipt_file, receipt)
    pending_before = run_json(
        t2ag_script, t2ag_root, "receipt-list-pending", "--activity", "AR-9001"
    )
    before_t2ag = manifest(t2ag_root)
    before_reading = manifest(reading_root)
    owner_response = run_json(
        reading_script,
        reading_root,
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(receipt_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "receipt-owner-apply", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag, "reading receipt application changed T2AG")
    require(
        changed_paths(before_reading, after_reading) == ["main/10_books/B901/pages/CH01/p0001.md"],
        "reading receipt application changed an unexpected reading path",
    )
    response_file = exchange / "owner-response.json"
    write_json(response_file, owner_response)
    before_t2ag = after_t2ag
    before_reading = after_reading
    owner_replay = run_json(
        reading_script,
        reading_root,
        "use-note",
        "--book",
        "B901",
        "--receipt-file",
        str(receipt_file),
    )
    after_t2ag = manifest(t2ag_root)
    after_reading = manifest(reading_root)
    record_transition(
        transitions, "receipt-owner-replay", before_t2ag, before_reading, after_t2ag, after_reading
    )
    require(after_t2ag == before_t2ag and after_reading == before_reading, "owner replay wrote state")
    before_ack_t2ag = after_t2ag
    before_ack_reading = after_reading
    ack = run_json(t2ag_script, t2ag_root, "receipt-ack", "--response-file", str(response_file))
    after_ack_t2ag = manifest(t2ag_root)
    after_ack_reading = manifest(reading_root)
    record_transition(
        transitions, "receipt-ack", before_ack_t2ag, before_ack_reading, after_ack_t2ag, after_ack_reading
    )
    require(
        changed_paths(before_ack_t2ag, after_ack_t2ag)
        == ["main/10_student/activities/reading/AR-9001.contributions.json"],
        "receipt ack changed an unexpected T2AG path",
    )
    require(after_ack_reading == before_ack_reading, "receipt ack changed reading state")
    before_ack_replay_t2ag = after_ack_t2ag
    before_ack_replay_reading = after_ack_reading
    ack_replay = run_json(
        t2ag_script,
        t2ag_root,
        "receipt-ack",
        "--response-file",
        str(response_file),
    )
    after_ack_replay_t2ag = manifest(t2ag_root)
    after_ack_replay_reading = manifest(reading_root)
    record_transition(
        transitions,
        "receipt-ack-replay",
        before_ack_replay_t2ag,
        before_ack_replay_reading,
        after_ack_replay_t2ag,
        after_ack_replay_reading,
    )
    require(
        before_ack_replay_t2ag == after_ack_replay_t2ag
        and before_ack_replay_reading == after_ack_replay_reading,
        "ack replay wrote state",
    )
    negative_before_t2ag = after_ack_replay_t2ag
    negative_before_reading = after_ack_replay_reading
    conflicting_receipt = list(receipt_arguments)
    conflicting_receipt[conflicting_receipt.index("--purpose") + 1] = "conflicting same-ID purpose"
    run_fail(t2ag_script, t2ag_root, *conflicting_receipt)
    invalid_consumer = list(receipt_arguments)
    invalid_consumer[invalid_consumer.index("--receipt-id") + 1] = "RCP-LOOP000000000099"
    invalid_consumer[invalid_consumer.index("--consumer-uri") + 1] = "t2ag://path/main/missing.md"
    run_fail(t2ag_script, t2ag_root, *invalid_consumer)
    conflicting_ack = dict(owner_response)
    conflicting_ack["result"] = "already_applied"
    conflicting_ack_file = exchange / "owner-conflicting-response.json"
    write_json(conflicting_ack_file, conflicting_ack)
    run_fail(t2ag_script, t2ag_root, "receipt-ack", "--response-file", str(conflicting_ack_file))
    negative_after_t2ag = manifest(t2ag_root)
    negative_after_reading = manifest(reading_root)
    record_transition(
        transitions,
        "negative-conflicts",
        negative_before_t2ag,
        negative_before_reading,
        negative_after_t2ag,
        negative_after_reading,
    )
    require(
        negative_before_t2ag == negative_after_t2ag
        and negative_before_reading == negative_after_reading,
        "negative conflict path wrote state",
    )
    pending_after = run_json(
        t2ag_script, t2ag_root, "receipt-list-pending", "--activity", "AR-9001"
    )

    ledger_path = t2ag_root / "main/10_student/activities/reading/AR-9001.contributions.json"
    context_store_path = reading_root / "main/10_books/B901/t2ag_context.json"
    page_path = reading_root / "main/10_books/B901/pages/CH01/p0001.md"
    ledger = load_json(ledger_path)
    context_store = load_json(context_store_path)
    page_text = page_path.read_text(encoding="utf-8")

    require(context_import["result"] == "imported", "context was not imported")
    require(context_replay["result"] == "already_processed", "context replay was not idempotent")
    require(contribution_import["result"] == "imported", "contribution was not imported")
    require(contribution_replay["result"] == "already_processed", "contribution replay was not idempotent")
    require(len(pending_before) == 1, "receipt was not pending exactly once")
    require(owner_response["result"] == "applied", "reading owner did not apply receipt")
    require(owner_replay["result"] == "already_applied", "reading receipt replay was not idempotent")
    require(ack["result"] == "acknowledged", "T2AG did not acknowledge owner response")
    require(ack_replay["result"] == "already_acknowledged", "ack replay was not idempotent")
    require(pending_after == [], "acknowledged receipt remained pending")
    require(len(ledger["contributions"]) == 1, "contribution ledger cardinality drifted")
    require(len(ledger["receipt_outbox"]) == 1, "receipt outbox cardinality drifted")
    require(ledger["receipt_outbox"][0]["status"] == "acknowledged", "receipt was not acknowledged")
    require(len(context_store["contexts"]) == 1, "reading context cardinality drifted")
    require(len(context_store["processed_events"]) == 1, "context event cardinality drifted")
    require(page_text.count("READING_USE_RECEIPT_V1") == 1, "receipt was duplicated in the note")
    recovery_cases = run_recovery_cases(
        fixture / "recovery-cases", t2ag_script, reading_script, contracts
    )

    return {
        "status": "pass",
        "fixture_book_deviation": "B901 used because reading-system book IDs require B[0-9]{3,}; literal TB001 is invalid",
        "manifest_transitions": transitions,
        "recovery_cases": recovery_cases,
        "roots": {"t2ag": str(t2ag_root), "reading": str(reading_root)},
        "context": {
            "export_id": context["export_id"],
            "store_sha256": file_sha(context_store_path),
            "count": len(context_store["contexts"]),
        },
        "contribution": {
            "contribution_id": contribution["contribution_id"],
            "count": len(ledger["contributions"]),
        },
        "receipt": {
            "receipt_id": receipt["receipt_id"],
            "status": ledger["receipt_outbox"][0]["status"],
            "note_marker_count": page_text.count("READING_USE_RECEIPT_V1"),
        },
        "replay": {
            "context": context_replay["result"],
            "contribution": contribution_replay["result"],
            "receipt": owner_replay["result"],
            "ack": ack_replay["result"],
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--reading-script", required=True)
    result.add_argument("--temp-root", required=True)
    result.add_argument("--t2ag-script", default=str(DEFAULT_T2AG_SCRIPT))
    result.add_argument("--contracts", default=str(DEFAULT_CONTRACTS))
    result.add_argument("--keep", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    temp_root = Path(args.temp_root).resolve()
    t2ag_script = Path(args.t2ag_script).resolve()
    reading_script = Path(args.reading_script).resolve()
    contracts = Path(args.contracts).resolve()
    if not temp_root.is_dir():
        print(f"[FAIL] temp root does not exist: {temp_root}", file=sys.stderr)
        return 2
    if not t2ag_script.is_file() or not reading_script.is_file() or not contracts.is_dir():
        print("[FAIL] script or contract source is missing", file=sys.stderr)
        return 2
    fixture = Path(tempfile.mkdtemp(prefix="t2ag-021-loop-", dir=temp_root))
    try:
        report = run_saga(fixture, t2ag_script, reading_script, contracts)
        report["fixture_root"] = str(fixture)
        report["kept"] = bool(args.keep)
        print(canonical_bytes(report).decode("utf-8"))
        return 0
    except (SagaError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            resolved = fixture.resolve()
            if resolved.parent != temp_root:
                raise SagaError(f"refusing to clean unexpected fixture path: {resolved}")
            shutil.rmtree(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
