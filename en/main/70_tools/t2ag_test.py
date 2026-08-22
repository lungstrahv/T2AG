#!/usr/bin/env python3
"""Select durable T2AG tests from a manifest and execute an in-memory plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import validation_control


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
DEFAULT_MANIFEST = TOOLS / "test_dependencies.json"
SCHEMA = "t2ag.test_dependencies.v2"


class TestPlanError(RuntimeError):
    pass


def no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TestPlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TestPlanError(f"cannot load manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise TestPlanError(f"manifest schema must be {SCHEMA}")
    tiers = value.get("tiers")
    tests = value.get("tests")
    components = value.get("components")
    if tiers != ["fast", "deep", "release_only"]:
        raise TestPlanError("tiers must be fast, deep, release_only in that order")
    if not isinstance(tests, dict) or not tests:
        raise TestPlanError("tests must be a non-empty object")
    if not isinstance(components, dict) or not components:
        raise TestPlanError("components must be a non-empty object")

    registered_paths: set[str] = set()
    for test_id, spec in tests.items():
        if not isinstance(test_id, str) or not isinstance(spec, dict):
            raise TestPlanError("test entries must be named objects")
        relative = spec.get("path")
        tier = spec.get("tier")
        kind = spec.get("kind")
        automatic = spec.get("automatic", True)
        if (
            not isinstance(relative, str)
            or "\\" in relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not relative.endswith(".py")
        ):
            raise TestPlanError(f"invalid test path for {test_id}: {relative!r}")
        if relative in registered_paths:
            raise TestPlanError(f"test path registered twice: {relative}")
        if tier not in tiers or kind not in {"atomic", "scenario"} or not isinstance(automatic, bool):
            raise TestPlanError(f"invalid tier/kind/automatic flag for {test_id}")
        relative_path = Path(relative)
        if kind == "atomic" and (
            relative_path.parent != Path("main/70_tools")
            or not relative_path.name.startswith("test_")
        ):
            raise TestPlanError(f"atomic test must be a direct test_* entry: {test_id}")
        if kind == "scenario" and (
            relative_path.parent != Path("main/70_tools/scenarios")
            or relative_path.name.startswith("test_")
        ):
            raise TestPlanError(f"scenario must be outside ordinary test discovery: {test_id}")
        if automatic is False and kind != "scenario":
            raise TestPlanError(f"only an explicit scenario may be non-automatic: {test_id}")
        if not (REPO / relative).is_file():
            raise TestPlanError(f"registered test is missing: {relative}")
        registered_paths.add(relative)

    referenced: set[str] = set()
    for component, spec in components.items():
        if not isinstance(component, str) or not isinstance(spec, dict):
            raise TestPlanError("component entries must be named objects")
        sources = spec.get("sources")
        component_tests = spec.get("tests")
        aggregate = spec.get("aggregate", False)
        plan_only = spec.get("plan_only", False)
        if (
            not isinstance(aggregate, bool)
            or not isinstance(plan_only, bool)
            or not isinstance(sources, list)
        ):
            raise TestPlanError(f"component {component} has invalid sources")
        if plan_only and not aggregate:
            raise TestPlanError(f"only an aggregate component may require plan-only use: {component}")
        if aggregate:
            if sources:
                raise TestPlanError(f"aggregate component {component} must not map changed paths")
        elif not sources or not all(isinstance(source, str) and source for source in sources):
            raise TestPlanError(f"component {component} has invalid sources")
        if not isinstance(component_tests, list) or not component_tests:
            raise TestPlanError(f"component {component} has no tests")
        unknown = [test_id for test_id in component_tests if test_id not in tests]
        if unknown:
            raise TestPlanError(f"component {component} references unknown tests: {unknown}")
        referenced.update(component_tests)
    unreferenced = sorted(set(tests) - referenced)
    if unreferenced:
        raise TestPlanError(f"tests are not assigned to any component: {unreferenced}")

    discovered = {
        path.relative_to(REPO).as_posix()
        for path in TOOLS.glob("test_*.py")
        if path.is_file()
    }
    registered_discovery = {
        relative
        for relative in registered_paths
        if Path(relative).parent == Path("main/70_tools")
        and Path(relative).name.startswith("test_")
    }
    if discovered != registered_discovery:
        raise TestPlanError(
            "ordinary test inventory differs from manifest: "
            f"missing={sorted(discovered - registered_discovery)} "
            f"stale={sorted(registered_discovery - discovered)}"
        )
    return value


def normalize_changed(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(REPO.resolve())
        except ValueError as exc:
            raise TestPlanError(f"changed path is outside repository: {value}") from exc
    normalized = path.as_posix().lstrip("./")
    if not normalized or normalized.startswith("../"):
        raise TestPlanError(f"invalid changed path: {value}")
    return normalized


def source_matches(changed: str, source: str) -> bool:
    source = source.rstrip("/")
    return changed == source or changed.startswith(source + "/")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    *,
    requested_components: list[str],
    requested_test_ids: list[str],
    changed_paths: list[str],
    tier: str,
) -> dict[str, Any]:
    components = manifest["components"]
    unknown = sorted(set(requested_components) - set(components))
    if unknown:
        raise TestPlanError(f"unknown components: {unknown}")
    unknown_tests = sorted(set(requested_test_ids) - set(manifest["tests"]))
    if unknown_tests:
        raise TestPlanError(f"unknown test IDs: {unknown_tests}")
    normalized_changed = [normalize_changed(path) for path in changed_paths]
    excluded = workflow["ordinary_budget"]["excluded_paths"]
    excluded_changed = [
        changed
        for changed in normalized_changed
        if any(source_matches(changed, prefix) for prefix in excluded)
    ]
    if excluded_changed and tier != "release_only":
        raise TestPlanError(f"changed paths are excluded from ordinary validation: {excluded_changed}")
    matched = set(requested_components)
    unmatched_changed: list[str] = []
    for changed in normalized_changed:
        hits = {
            component
            for component, spec in components.items()
            if not spec.get("aggregate", False)
            if any(source_matches(changed, source) for source in spec["sources"])
        }
        if not hits:
            unmatched_changed.append(changed)
        matched.update(hits)
    if unmatched_changed:
        raise TestPlanError(f"changed paths have no dependency mapping: {unmatched_changed}")
    if not matched and not requested_test_ids:
        raise TestPlanError("select at least one --component, --test or --changed path")

    requested_tests = [
        test_id for test_id in manifest["tests"] if test_id in set(requested_test_ids)
    ]
    for component in components:
        if component in matched:
            for test_id in components[component]["tests"]:
                if test_id not in requested_tests:
                    requested_tests.append(test_id)

    tier_rank = {name: index for index, name in enumerate(manifest["tiers"])}
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for test_id in requested_tests:
        spec = manifest["tests"][test_id]
        row = {
            "id": test_id,
            "path": spec["path"],
            "tier": spec["tier"],
            "kind": spec["kind"],
            "sha256": sha256_file(REPO / spec["path"]),
        }
        if tier_rank[spec["tier"]] > tier_rank[tier]:
            deferred.append({**row, "reason": f"requires_{spec['tier']}"})
        elif not spec.get("automatic", True):
            deferred.append({**row, "reason": "scenario_requires_explicit_invocation"})
        else:
            selected.append(row)

    body = {
        "schema": "t2ag.test_plan.v1",
        "tier": tier,
        "components": sorted(matched),
        "requested_test_ids": requested_test_ids,
        "changed_paths": normalized_changed,
        "plan_only_required": any(components[name].get("plan_only", False) for name in matched),
        "selected": selected,
        "deferred": deferred,
        "commands": [["python", "-B", row["path"]] for row in selected],
        "ordinary_budget": {
            "applies": tier != "release_only",
            "max_test_commands": workflow["ordinary_budget"]["max_test_commands"],
            "selected_test_commands": len(selected),
            "within_budget": (
                tier == "release_only"
                or len(selected) <= workflow["ordinary_budget"]["max_test_commands"]
            ),
        },
        "release_execution_requires_reason": tier == "release_only",
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**body, "plan_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--workflow", type=Path, default=validation_control.DEFAULT_WORKFLOW)
    parser.add_argument("--component", action="append", default=[])
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--changed", action="append", default=[])
    parser.add_argument("--tier", choices=("fast", "deep", "release_only"), default="fast")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--execute-plan")
    parser.add_argument("--release-reason")
    parser.add_argument("--list", action="store_true", dest="list_manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest.resolve())
        workflow = validation_control.load_workflow(args.workflow.resolve())
        if args.list_manifest:
            print(json.dumps({
                "schema": manifest["schema"],
                "components": manifest["components"],
                "tests": manifest["tests"],
                "validation_workflow": workflow,
            }, ensure_ascii=False, indent=2))
            return 0
        plan = build_plan(
            manifest,
            workflow,
            requested_components=args.component,
            requested_test_ids=args.test,
            changed_paths=args.changed,
            tier=args.tier,
        )
    except (TestPlanError, validation_control.ValidationControlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan_only and args.execute_plan:
        print("ERROR: --plan-only and --execute-plan cannot be combined", file=sys.stderr)
        return 2
    if args.plan_only or not args.execute_plan:
        print("PLAN ONLY: review the selection, then rerun with --execute-plan <plan_sha256>.")
        return 0
    if args.execute_plan != plan["plan_sha256"]:
        print("ERROR: --execute-plan does not match the current test plan", file=sys.stderr)
        return 2
    if plan["plan_only_required"]:
        print("ERROR: selected aggregate is plan-only; execute its domain components explicitly", file=sys.stderr)
        return 2
    if not plan["ordinary_budget"]["within_budget"]:
        print("ERROR: ordinary plan exceeds the three-test-command budget; narrow the selection", file=sys.stderr)
        return 2
    if plan["release_execution_requires_reason"]:
        if args.release_reason not in workflow["release_execution_reasons"]:
            print(
                "ERROR: release-only execution requires --release-reason from validation_workflow.json",
                file=sys.stderr,
            )
            return 2
    elif args.release_reason:
        print("ERROR: --release-reason is valid only for release_only execution", file=sys.stderr)
        return 2
    if not plan["selected"]:
        print("ERROR: selection contains no automatically runnable tests", file=sys.stderr)
        return 2
    started = time.monotonic()
    max_seconds = workflow["ordinary_budget"]["max_minutes"] * 60
    for row in plan["selected"]:
        print(f"RUN {row['id']} -> {row['path']}", flush=True)
        timeout = None
        if plan["ordinary_budget"]["applies"]:
            timeout = max_seconds - (time.monotonic() - started)
            if timeout <= 0:
                print("ERROR: ordinary validation exceeded the ten-minute budget", file=sys.stderr)
                return 124
        try:
            result = subprocess.run(
                [sys.executable, "-B", str(REPO / row["path"])],
                cwd=REPO,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: ordinary validation exceeded the ten-minute budget", file=sys.stderr)
            return 124
        if result.returncode:
            print(f"FAIL {row['id']}: exit={result.returncode}", file=sys.stderr)
            return result.returncode
    print(f"result: {len(plan['selected'])}/{len(plan['selected'])} selected test files passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
