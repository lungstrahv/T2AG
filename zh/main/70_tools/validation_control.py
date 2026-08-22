#!/usr/bin/env python3
"""Load and compose the shared T2AG validation workflow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TOOLS = Path(__file__).resolve().parent
DEFAULT_WORKFLOW = TOOLS / "validation_workflow.json"
SCHEMA = "t2ag.validation_workflow.v1"


class ValidationControlError(RuntimeError):
    pass


def no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationControlError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def profile_check_ids(workflow: dict[str, Any], profile: str) -> list[str]:
    profiles = workflow["profiles"]
    if profile not in profiles:
        raise ValidationControlError(f"unknown Doctor profile: {profile}")
    spec = profiles[profile]
    result: list[str] = []
    parent = spec.get("extends")
    if parent is not None:
        result.extend(profile_check_ids(workflow, parent))
    for check_id in spec["checks"]:
        if check_id not in result:
            result.append(check_id)
    return result


def load_workflow(path: Path = DEFAULT_WORKFLOW) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationControlError(f"cannot load workflow {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValidationControlError(f"workflow schema must be {SCHEMA}")

    checks = value.get("doctor_checks")
    profiles = value.get("profiles")
    levels = value.get("validation_levels")
    guards = value.get("guards")
    budget = value.get("ordinary_budget")
    reasons = value.get("release_execution_reasons")
    if not isinstance(checks, dict) or not checks:
        raise ValidationControlError("doctor_checks must be a non-empty object")
    if not isinstance(profiles, dict) or set(profiles) != {"runtime", "release"}:
        raise ValidationControlError("profiles must be exactly runtime and release")
    if not isinstance(levels, dict) or set(levels) != {"V0", "V1", "V2", "V3"}:
        raise ValidationControlError("validation_levels must be exactly V0-V3")
    if not isinstance(guards, dict) or not isinstance(budget, dict):
        raise ValidationControlError("guards and ordinary_budget must be objects")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(x, str) and x for x in reasons):
        raise ValidationControlError("release_execution_reasons must be non-empty strings")

    for check_id, spec in checks.items():
        if not isinstance(check_id, str) or not isinstance(spec, dict):
            raise ValidationControlError("Doctor checks must be named objects")
        if spec.get("phase") not in {"runtime", "release"}:
            raise ValidationControlError(f"invalid phase for Doctor check {check_id}")
        if not isinstance(spec.get("handler"), str) or not spec["handler"]:
            raise ValidationControlError(f"missing handler for Doctor check {check_id}")
        dependencies = spec.get("depends_on")
        if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
            raise ValidationControlError(f"invalid dependencies for Doctor check {check_id}")
        unknown = sorted(set(dependencies) - set(checks))
        if unknown:
            raise ValidationControlError(f"unknown dependencies for {check_id}: {unknown}")
        if check_id in dependencies:
            raise ValidationControlError(f"Doctor check depends on itself: {check_id}")

    assigned: list[str] = []
    for profile, spec in profiles.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("checks"), list):
            raise ValidationControlError(f"invalid Doctor profile: {profile}")
        if len(spec["checks"]) != len(set(spec["checks"])):
            raise ValidationControlError(f"duplicate checks in Doctor profile: {profile}")
        unknown = sorted(set(spec["checks"]) - set(checks))
        if unknown:
            raise ValidationControlError(f"unknown checks in Doctor profile {profile}: {unknown}")
        assigned.extend(spec["checks"])
    if profiles["runtime"].get("extends") is not None or profiles["runtime"].get("default") is not True:
        raise ValidationControlError("runtime must be the unextended default Doctor profile")
    if profiles["release"].get("extends") != "runtime" or profiles["release"].get("explicit_only") is not True:
        raise ValidationControlError("release must explicitly extend runtime")
    if len(assigned) != len(set(assigned)) or set(assigned) != set(checks):
        raise ValidationControlError("every Doctor check must be assigned to exactly one profile")
    for check_id in profiles["runtime"]["checks"]:
        if checks[check_id]["phase"] != "runtime":
            raise ValidationControlError(f"runtime profile contains non-runtime check: {check_id}")
    for check_id in profiles["release"]["checks"]:
        if checks[check_id]["phase"] != "release":
            raise ValidationControlError(f"release profile contains non-release check: {check_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(check_id: str) -> None:
        if check_id in visiting:
            raise ValidationControlError(f"Doctor dependency cycle at {check_id}")
        if check_id in visited:
            return
        visiting.add(check_id)
        for dependency in checks[check_id]["depends_on"]:
            visit(dependency)
        visiting.remove(check_id)
        visited.add(check_id)

    for check_id in checks:
        visit(check_id)
    for profile in profiles:
        allowed = set(profile_check_ids(value, profile))
        missing_dependencies = sorted({
            dependency
            for check_id in allowed
            for dependency in checks[check_id]["depends_on"]
            if dependency not in allowed
        })
        if missing_dependencies:
            raise ValidationControlError(
                f"profile {profile} excludes required dependencies: {missing_dependencies}"
            )

    expected_guards = {
        "default_profile": "runtime",
        "release_explicit_only": True,
        "release_plan_binding_required": True,
        "release_suite_plan_only": True,
        "no_implicit_tier_escalation": True,
    }
    if any(guards.get(key) != expected for key, expected in expected_guards.items()):
        raise ValidationControlError("validation escalation guards are incomplete")
    if budget.get("max_agents") != 1 or budget.get("max_test_commands") != 3 or budget.get("max_minutes") != 10:
        raise ValidationControlError("ordinary validation budget must remain 1 agent/3 tests/10 minutes")
    excluded = budget.get("excluded_paths")
    if not isinstance(excluded, list) or not all(isinstance(x, str) and x for x in excluded):
        raise ValidationControlError("ordinary excluded_paths must be non-empty strings")
    return value


def build_doctor_plan(
    workflow: dict[str, Any],
    *,
    profile: str,
    requested_checks: list[str],
) -> dict[str, Any]:
    allowed = profile_check_ids(workflow, profile)
    allowed_set = set(allowed)
    unknown = sorted(set(requested_checks) - allowed_set)
    if unknown:
        raise ValidationControlError(f"checks are outside profile {profile}: {unknown}")

    if requested_checks:
        selected_set: set[str] = set()

        def include(check_id: str) -> None:
            for dependency in workflow["doctor_checks"][check_id]["depends_on"]:
                include(dependency)
            selected_set.add(check_id)

        for check_id in requested_checks:
            include(check_id)
        selected_ids = [check_id for check_id in allowed if check_id in selected_set]
        scope = "targeted"
    else:
        selected_ids = allowed
        scope = "full"

    rows = [
        {
            "id": check_id,
            "phase": workflow["doctor_checks"][check_id]["phase"],
            "handler": workflow["doctor_checks"][check_id]["handler"],
            "depends_on": workflow["doctor_checks"][check_id]["depends_on"],
        }
        for check_id in selected_ids
    ]
    body = {
        "schema": "t2ag.doctor_plan.v1",
        "profile": profile,
        "scope": scope,
        "claimable_profile_result": scope == "full",
        "release_execution_requires_reason": profile == "release",
        "checks": rows,
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**body, "plan_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
