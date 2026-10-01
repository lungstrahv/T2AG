"""Portable, explicit-entry command line. JSON errors never imply a saved fact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .model import DomainError, require, parse_json
from .journal import Journal


def _json_file(path):
    return parse_json(Path(path).read_text(encoding="utf-8-sig"))


def parser():
    p = argparse.ArgumentParser(prog="t2ag-next", description="T2AG explicit, durable learning operations")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--instance", default="instance")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--language", choices=("zh", "en"), required=True)
    init.add_argument("--profile")
    act = sub.add_parser("act")
    act.add_argument("request", help="UTF-8 JSON request file, or - for stdin")
    lookup = sub.add_parser("lookup")
    lookup.add_argument("request_id")
    con = sub.add_parser("context")
    con.add_argument("--entry", choices=("entry.teach", "entry.maintain", "entry.audit", "entry.release"), required=True)
    con.add_argument("--lane", choices=("teach", "maintain", "audit", "release"), required=True)
    con.add_argument("--scope")
    con.add_argument("--session")
    con.add_argument("--level", default="critical", choices=("critical", "L0", "L1", "L2"))
    ins = sub.add_parser("inspect")
    ins.add_argument("kind")
    ins.add_argument("identity", nargs="?")
    doc = sub.add_parser("doctor")
    group = doc.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true")
    group.add_argument("--changed", nargs="+")
    group.add_argument("--plan")
    negative = sub.add_parser("validate-negative")
    negative.add_argument("validation_id")
    negative.add_argument("request")
    negative.add_argument("expected_code")
    cloud_sync = sub.add_parser("cloud-sync")
    cloud_sync.add_argument("request", help="Explicit cloud.event.apply JSON; validates locally before a synced receipt")
    governance_plan = sub.add_parser("governance-plan")
    governance_plan.add_argument("--level", choices=("V0", "V1", "V2", "V3"), required=True)
    governance_plan.add_argument("--changed", nargs="+")
    governance_plan.add_argument("--files", nargs="+")
    governance_plan.add_argument("--release-reason")
    governance_plan.add_argument("--package")
    governance_plan.add_argument("--case-matrix")
    governance_run = sub.add_parser("governance-run")
    governance_run.add_argument("run_id")
    governance_run.add_argument("plan")
    governance_run.add_argument("execute_plan_sha")
    governance_review = sub.add_parser("governance-review")
    governance_review.add_argument("review_id")
    governance_review.add_argument("blob_sha256")
    rebind = sub.add_parser("rebind-assets")
    rebind.add_argument("request_id")
    state = sub.add_parser("state")
    state.add_argument("--write", action="store_true")
    blob = sub.add_parser("blob")
    blob.add_argument("file")
    sub.add_parser("actions")
    workflow = sub.add_parser("workflow", help="Read a short task loop; this never executes it")
    workflow.add_argument("name", nargs="?")
    workflow.add_argument("--language", choices=("zh", "en"), default="en")
    sub.add_parser("identity")
    history = sub.add_parser("history", help="List retained history or follow an old locator")
    history.add_argument("locator", nargs="?")
    export_context = sub.add_parser("context-export")
    export_context.add_argument("scope")
    export_context.add_argument("identity")
    reading_export = sub.add_parser("reading-context-export")
    reading_export.add_argument("activity_id")
    reading_export.add_argument("event_id")
    reading_export.add_argument("generated_at")
    evidence = sub.add_parser("evidence")
    evidence.add_argument("sha256")
    evidence.add_argument("--output")
    dist = sub.add_parser("package")
    dist.add_argument("root")
    dist.add_argument("output")
    verify_package = sub.add_parser("package-verify")
    verify_package.add_argument("package")
    install = sub.add_parser("install")
    install.add_argument("package")
    install.add_argument("destination")
    install.add_argument("--language", choices=("zh", "en"), required=True)
    upgrade = sub.add_parser("upgrade")
    upgrade.add_argument("package")
    upgrade.add_argument("current_installation")
    upgrade.add_argument("destination")
    lite = sub.add_parser("lite")
    lite.add_argument("root")
    lite.add_argument("destination")
    lite.add_argument("--write", action="store_true")
    okf = sub.add_parser("okf")
    okf.add_argument("root")
    okf.add_argument("--destination")
    okf.add_argument("--course-definition")
    okf.add_argument("--write", action="store_true")
    okf_check = sub.add_parser("okf-check")
    okf_check.add_argument("bundle")
    projection_rollback = sub.add_parser("projection-rollback")
    projection_rollback.add_argument("destination")
    projection_rollback.add_argument("receipt")
    projection_rollback.add_argument("--write", action="store_true")
    guide = sub.add_parser("guide")
    guide.add_argument("root")
    guide.add_argument("destination")
    guide.add_argument("--language", choices=("zh", "en"), required=True)
    assets = sub.add_parser("assets")
    ats = assets.add_subparsers(dest="asset_command", required=True)
    pdf = ats.add_parser("inspect")
    pdf.add_argument("source_id")
    warm = ats.add_parser("prewarm")
    warm.add_argument("source_id")
    warm.add_argument("pages", nargs="+", type=int)
    warm.add_argument("--dpi", type=int, default=300)
    warm.add_argument("--repair", action="store_true")
    layout = ats.add_parser("layout")
    layout.add_argument("source_id")
    layout.add_argument("pages", nargs="+", type=int)
    ats.add_parser("cache")
    gc = ats.add_parser("gc")
    gc.add_argument("--keep", action="append", default=[])
    gc.add_argument("--older-than-seconds", type=int, default=86400)
    gc.add_argument("--apply-plan")
    migration = sub.add_parser("migrate")
    ms = migration.add_subparsers(dest="migration_command", required=True)
    export = ms.add_parser("export")
    export.add_argument("source")
    export.add_argument("package")
    verify = ms.add_parser("verify")
    verify.add_argument("package")
    imp = ms.add_parser("import")
    imp.add_argument("package")
    ms.add_parser("report")
    history = ms.add_parser("history")
    history.add_argument("--kind")
    history.add_argument("--course")
    return p


def run(args):
    from . import service
    command = args.command
    if command == "init":
        profile = _json_file(args.profile) if args.profile else {}
        require(isinstance(profile, dict), "PROFILE", "Profile must be an object.")
        profile.setdefault("language", args.language)
        require(profile["language"] == args.language, "LANGUAGE_CONFLICT", "Profile and selected edition language differ.")
        profile.setdefault("facts_status", "not_provided")
        return Journal(args.instance).initialize(profile)
    if command == "act":
        request = parse_json(sys.stdin.read()) if args.request == "-" else _json_file(args.request)
        return service.execute(args.instance, request)
    if command == "lookup":
        return {"receipt": Journal(args.instance).lookup(args.request_id)}
    if command == "context":
        return service.context(args.instance, entry=args.entry, session_lane=args.lane, scope=args.scope, session_id=args.session, level=args.level)
    if command == "inspect":
        state = Journal(args.instance).read_state()
        if args.identity:
            identity, data = service.resolve(state, args.kind, args.identity)
            entity = state["objects"][f"{args.kind}/{identity}"]
            return {"revision": state["revision"], **entity}
        return {"revision": state["revision"], "objects": [e for e in state["objects"].values() if e["kind"] == args.kind]}
    if command == "doctor":
        return service.doctor(args.instance, full=args.full, changed_kinds=args.changed, plan=_json_file(args.plan) if args.plan else None)
    if command == "validate-negative":
        return service.validate_negative(args.instance, args.validation_id, _json_file(args.request), args.expected_code)
    if command == "cloud-sync":
        from .cloud import sync_event
        return sync_event(args.instance, _json_file(args.request))
    if command == "governance-plan":
        from .governance import build_validation_plan
        return build_validation_plan(Journal(args.instance).read_state(), level=args.level,
            changed_kinds=args.changed, changed_files=args.files, release_reason=args.release_reason,
            package=args.package, case_matrix_id=args.case_matrix)
    if command == "governance-run":
        from .governance import run_validation
        return run_validation(args.instance, args.run_id, _json_file(args.plan), args.execute_plan_sha)
    if command == "governance-review":
        from .governance import import_review
        return import_review(args.instance, args.review_id, args.blob_sha256)
    if command == "rebind-assets":
        return Journal(args.instance).rebind_assets(args.request_id)
    if command == "state":
        return service.refresh(args.instance, args.write)
    if command == "blob":
        return Journal(args.instance).put_file(args.file)
    if command == "actions":
        return {"version": __version__, "actions": service.actions()}
    if command == "workflow":
        from .workflows import get_workflow, list_workflows
        return get_workflow(args.name, args.language) if args.name else {"workflows": list_workflows(args.language)}
    if command == "identity":
        result = Journal(args.instance).validate()
        return {"instance_id": result["instance_id"], "revision": result["revision"]}
    if command == "history":
        from .continuity import history_index, resolve_history
        state = Journal(args.instance).read_state()
        return resolve_history(state, args.locator) if args.locator else history_index(state)
    if command == "context-export":
        from .exchange import context_export
        return context_export(Journal(args.instance).read_state(), args.identity, args.scope)
    if command == "reading-context-export":
        from .reading_bridge import context_export
        return context_export(Journal(args.instance).read_state(), args.activity_id, args.event_id, args.generated_at)
    if command == "evidence":
        data = Journal(args.instance).read_blob(args.sha256)
        if args.output:
            from .distribution import _destination
            path = _destination(args.output, args.instance)
            with path.open("xb") as f:
                f.write(data)
            return {"ok": True, "path": str(path), "bytes": len(data), "sha256": args.sha256}
        try:
            body = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            body = None
        return {"ok": True, "sha256": args.sha256, "bytes": len(data), "utf8_text": body,
                "next_action": None if body is not None else "Use --output to inspect original binary evidence."}
    if command == "okf-check":
        from .distribution_projection import check_bundle
        return check_bundle(args.bundle)
    if command == "projection-rollback":
        from .distribution_projection import rollback_projection
        return rollback_projection(args.destination, args.receipt, write=args.write)
    if command in ("package", "package-verify", "install", "upgrade", "lite", "okf", "guide"):
        from . import distribution
        if command == "package": return distribution.build_distribution(args.root, args.output)
        if command == "package-verify": return distribution.verify_distribution(args.package)
        if command == "install": return distribution.install(args.package, args.destination, args.language)
        if command == "upgrade": return distribution.upgrade(args.package, args.current_installation, args.destination)
        if command == "lite": return distribution.lite_projection(args.root, args.destination, write=args.write)
        if command == "guide": return distribution.build_guide(args.root, args.destination, args.language)
        return distribution.okf_export(args.root, args.destination, course_definition=_json_file(args.course_definition) if args.course_definition else None, write=args.write)
    if command == "assets":
        from . import assets
        if args.asset_command == "inspect": return assets.inspect_pdf(args.instance, args.source_id)
        if args.asset_command == "prewarm": return assets.prewarm_pages(args.instance, args.source_id, args.pages, dpi=args.dpi, repair=args.repair)
        if args.asset_command == "layout": return assets.layout_scan(args.instance, args.source_id, args.pages)
        if args.asset_command == "cache": return assets.inspect_cache(args.instance)
        return assets.gc_cache(args.instance, keep_keys=args.keep, older_than_seconds=args.older_than_seconds, dry_run=args.apply_plan is None, expected_plan_sha256=args.apply_plan)
    if command == "migrate":
        from . import migration
        if args.migration_command == "export":
            return migration.export_legacy(args.source, args.package)
        if args.migration_command == "verify":
            return migration.verify_package(args.package)
        if args.migration_command == "import":
            return migration.import_package(args.package, args.instance)
        if args.migration_command == "history":
            return migration.migration_history(args.instance, kind=args.kind, course_id=args.course)
        return migration.migration_report(args.instance)
    raise DomainError("COMMAND", "Unknown command.")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if not isinstance(result, dict) or result.get("ok", True) else 1
    except DomainError as e:
        print(json.dumps(e.as_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as e:
        # An unexpected failure may have followed durable publication. The caller
        # must resolve the original request ID before retrying a changed request.
        result = {"ok": False, "code": "OPERATION_FAILED", "message": str(e), "persistence": "unknown",
                  "next_action": "For an act request, lookup its original request_id before retrying."}
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
