"""Explicit continuity for revised blocks, external references and history.

These transitions retain attributed semantic decisions. They do not certify
equivalence, read a peer repository, or grant permission to present new content.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import posixpath
import re

from . import learning, support
from .model import DomainError, fields, get, put, require


ACTIONS = {"continuity.remap", "external.relocate", "external.rebind", "history.redirect.register"}
ENTITY_KINDS = {"continuity_map", "external_revision", "history_redirect"}
HISTORY_KINDS = {"history", "adr", "evolution"}


def _actor(request):
    actor = support._provenance(request)
    require(actor["role"] in {"teacher", "student", "system"}, "CONTINUITY_ACTOR", "Use the actual local decision attribution.")
    require(isinstance(actor["text"], str) and bool(actor["text"].strip()), "CONTINUITY_ACTOR", "Retain the actual decision or technical reason.")
    return actor


def _identity(data):
    identity = data.get("identity")
    require(isinstance(identity, dict), "EXTERNAL_IDENTITY", "Bind peer_system and peer_relative_path separately from host root hints.")
    fields(identity, "peer_system", "peer_relative_path")
    path = identity["peer_relative_path"]
    require(isinstance(path, str) and bool(path) and not path.startswith("/") and "\\" not in path and ":" not in path
            and all(part not in {"", ".", ".."} for part in path.split("/")), "EXTERNAL_IDENTITY", "Peer identity is a stable safe relative locator, not an absolute host path.")
    require(isinstance(identity["peer_system"], str) and bool(identity["peer_system"].strip()), "EXTERNAL_IDENTITY", "Name the actual peer system.")
    return {name: identity[name] for name in ("peer_system", "peer_relative_path")}


def _reference_change(state, request, payload, actor):
    fields(payload, "id", "revision_id", "reason")
    current = support._read(state, request, "external", payload["id"])
    identity = _identity(current)
    before = deepcopy(current)
    if request["action"] == "external.relocate":
        # Imported T1 references use the original kind/usage_rule names. A
        # location-only move retains that known policy in the new consumer form.
        if not current.get("mode"):
            mode = {"frozen_version": "frozen", "living_data": "copy_on_use"}.get(current.get("kind"))
            require(mode is not None, "REFERENCE_MODE", "Resolve an unknown legacy reference policy before relocation.")
            current["mode"] = mode
        fields(payload, "root_hints")
        hints = payload["root_hints"]
        require(isinstance(hints, dict) and identity["peer_system"] in hints, "EXTERNAL_ROOT_HINT", "Give a host-location hint for the existing peer identity.")
        for hint in hints.values():
            require(isinstance(hint, dict), "EXTERNAL_ROOT_HINT", "Root hints contain windows_host and an optional resolution note.")
            fields(hint, "windows_host")
            require(isinstance(hint["windows_host"], str) and bool(hint["windows_host"].strip()), "EXTERNAL_ROOT_HINT", "A root hint is a nonempty location string.")
        current["root_hints"] = deepcopy(hints)
    else:
        fields(payload, "mode", "contract", "body", "observed_sha256", "effective_at")
        require(payload["mode"] in {"frozen", "copy_on_use"}, "REFERENCE_MODE", "Use an explicit reference policy.")
        require(isinstance(payload["body"], str), "EXTERNAL_BODY", "Bind the actual reference text used for this revision.")
        observed = sha256(payload["body"].encode("utf-8")).hexdigest()
        require(observed == payload["observed_sha256"], "CONTENT_HASH", "Reference revision must bind its actual original text.")
        if payload["mode"] == "frozen":
            fields(payload, "peer_version")
        current.update(mode=payload["mode"], contract=deepcopy(payload["contract"]), content_sha256=observed,
                       pinned_sha256=observed if payload["mode"] == "frozen" else None,
                       peer_version=payload.get("peer_version"), version=payload.get("peer_version"),
                       effective_at=payload["effective_at"], current_revision_id=payload["revision_id"])
    current["identity"] = identity
    current["last_change"] = {"revision_id": payload["revision_id"], "action": request["action"], "reason": payload["reason"], "actor": actor}
    revision = {"reference_id": payload["id"], "identity": identity, "before": before, "after": deepcopy(current),
                "change": deepcopy(payload), "actor": actor, "peer_accessed": False}
    return [support._new(state, "external_revision", payload["revision_id"], revision), put("external", payload["id"], current)]


def _same_source(old_blocks, new_block):
    """Check literal source containment; semantic equivalence stays attributed."""
    previous = [ref for block in old_blocks for ref in block.get("source_refs", [])]
    return bool(new_block.get("source_refs")) and all(
        any(ref["page_id"] == old["page_id"] and ref["source_excerpt"] in old["source_excerpt"] for old in previous)
        for ref in new_block["source_refs"])


def _remap(state, request, payload, actor):
    fields(payload, "id", "activity_id", "from_lessonmap_id", "to_lessonmap_id", "rows", "preparation_id", "receipts", "reason")
    aid = payload["activity_id"]
    activity = support._read(state, request, "activity", aid)
    require(activity["status"] == "ongoing", "CONTINUITY_ACTIVITY", "Revise an ongoing activity, not a closing or historical one.")
    old_map = get(state, "lessonmap", payload["from_lessonmap_id"])
    new_map = get(state, "lessonmap", payload["to_lessonmap_id"])
    current_prep = get(state, "preparation", activity["preparation_id"])
    require(current_prep["lessonmap_id"] == payload["from_lessonmap_id"], "CONTINUITY_SOURCE", "Map from the current prepared block structure.")
    require(old_map["activity_id"] == new_map["activity_id"] == aid and old_map["scope_id"] != new_map["scope_id"],
            "CONTINUITY_SCOPE", "Use two explicit Scope versions of this activity.")
    old_ids = set(old_map["block_ids"]) - set(new_map["block_ids"])
    new_ids = set(new_map["block_ids"]) - set(old_map["block_ids"])
    rows = payload["rows"]
    require(isinstance(rows, list) and bool(rows), "CONTINUITY_ROWS", "Describe the changed blocks explicitly.")
    seen_old, seen_new, effects, checkpoints = set(), set(), [], []
    for row in rows:
        fields(row, "kind", "from_block_ids", "to_block_ids", "reason", "checkpoint_links")
        previous, following = row["from_block_ids"], row["to_block_ids"]
        require(isinstance(previous, list) and isinstance(following, list) and len(previous) == len(set(previous)) and len(following) == len(set(following)), "CONTINUITY_ROWS", "Each row lists distinct block identities.")
        shape = {"split": len(previous) == 1 and len(following) > 1, "merge": len(previous) > 1 and len(following) == 1,
                 "renumber": len(previous) == len(following) == 1, "boundary_shift": bool(previous) and bool(following),
                 "retired": bool(previous) and not following, "new": not previous and bool(following)}
        require(shape.get(row["kind"], False), "CONTINUITY_KIND", "The mapping kind must describe its actual cardinality.")
        require(set(previous) <= old_ids and set(following) <= new_ids and not seen_old.intersection(previous) and not seen_new.intersection(following),
                "CONTINUITY_ROWS", "Every changed old and new block belongs to exactly one explicit row.")
        seen_old.update(previous); seen_new.update(following)
        old_blocks = [support._read(state, request, "block", bid) for bid in previous]
        new_blocks = {bid: support._read(state, request, "block", bid) for bid in following}
        require(all(block["activity_id"] == aid for block in old_blocks + list(new_blocks.values())), "CONTINUITY_ACTIVITY", "All mapped blocks belong to this activity.")
        require(all(block["status"] == "planned" for block in new_blocks.values()), "CONTINUITY_TARGET", "Map to new unpresented blocks; preserve prior teaching bodies unchanged.")
        for cid, checkpoint in support._all(state, "checkpoint"):
            if checkpoint.get("activity_id") == aid and checkpoint.get("block_id", checkpoint.get("position")) in previous:
                require(checkpoint["status"] in {"confirmed", "archived"}, "CONTINUITY_PENDING", "Close or explicitly defer an old checkpoint before removing its block.")
        for link in row["checkpoint_links"]:
            fields(link, "from_ids", "to_id", "to_block_id")
            require(link["to_block_id"] in following and bool(link["from_ids"]), "CONTINUITY_CHECKPOINT", "A preserved confirmation needs explicit predecessors and a mapped successor.")
            predecessors = [support._read(state, request, "checkpoint", cid) for cid in link["from_ids"]]
            require(all(cp["activity_id"] == aid and cp.get("block_id", cp.get("position")) in previous and cp["status"] == "confirmed" for cp in predecessors),
                    "CONTINUITY_CONFIRMATION", "Only actual confirmed predecessors may carry confirmed semantics.")
            require({cp.get("block_id", cp.get("position")) for cp in predecessors} == set(previous),
                    "CONTINUITY_CONFIRMATION", "A merged confirmation needs all mapped predecessor confirmations.")
            target = new_blocks[link["to_block_id"]]
            require(_same_source(old_blocks, target), "CONTINUITY_NEW_CONTENT", "New source material does not inherit a previous confirmation.")
            require(link["to_id"] not in checkpoints, "CONTINUITY_CHECKPOINT", "A successor checkpoint is defined once.")
            checkpoints.append(link["to_id"])
            effects.append(support._new(state, "checkpoint", link["to_id"], {"activity_id": aid, "block_id": link["to_block_id"],
                "position": target["teacher_title"], "status": "confirmed", "evidence": [{"continuity_map": payload["id"], "predecessor_ids": link["from_ids"]}],
                "confirmation_basis": "preserved_predecessor_fact_with_attributed_mapping", "provenance": actor}))
        if row["kind"] == "new":
            require(not row["checkpoint_links"], "CONTINUITY_NEW_CONTENT", "A new block has no inherited checkpoint.")
    require(seen_old == old_ids and seen_new == new_ids, "CONTINUITY_INCOMPLETE", "Account for every changed block, including new and retired content.")
    cursor = support._read(state, request, "cursor", aid)
    before_cursor = deepcopy(cursor)
    if cursor.get("block_id") in old_ids:
        require(cursor.get("waiting_for") in {"authorization", "ready", "start"}, "CONTINUITY_OPEN_GATE", "Resolve the actual response/feeling/question gate before changing its teaching body.")
        fields(payload, "resume_block_id")
        target_id = payload["resume_block_id"]
        row = next(row for row in rows if cursor["block_id"] in row["from_block_ids"])
        require(target_id in row["to_block_ids"], "CONTINUITY_RESUME", "Choose the exact successor within the current block's mapping.")
        target = get(state, "block", target_id)
        cursor.update(block_id=target_id, position=target["teacher_title"], waiting_for="authorization", next_action="authorize_mapped_block",
                      pending_body=None, body_sha256=target["body_sha256"], continuity_map_id=payload["id"])
        effects.append(put("cursor", aid, cursor))
    # Reuse the normal preparation checks; the mapping grants no source scan.
    prep_request = {**request, "action": "preparation.create", "payload": {"preparation_id": payload["preparation_id"],
        "activity_id": aid, "scope_id": new_map["scope_id"], "lessonmap_id": payload["to_lessonmap_id"], "receipts": payload["receipts"]}}
    # Preparation is a teacher technical operation even when a student initiated
    # the organization change; original decision attribution stays in the map.
    prep_request["actor"] = {"role": "teacher", "source": actor["source"], "text": "Apply the explicitly attributed block mapping and normal preparation checks."}
    effects.extend(learning.plan(state, prep_request))
    for sid, session in support._all(state, "session"):
        if session.get("activity_id") == aid and session.get("status") == "active":
            session = support._read(state, request, "session", sid)
            session.update(status="closed", saved_cursor=before_cursor, closed_by_mapping=payload["id"])
            effects.append(put("session", sid, session))
    for tid, ticket in support._all(state, "ticket"):
        if ticket.get("activity_id") == aid and ticket.get("status") == "issued":
            ticket = support._read(state, request, "ticket", tid); ticket.update(status="expired", expired_by_mapping=payload["id"])
            effects.append(put("ticket", tid, ticket))
    record = {**deepcopy(payload), "actor": actor, "cursor_before": before_cursor, "cursor_after": cursor,
              "old_lessonmap_order": old_map["block_ids"], "new_lessonmap_order": new_map["block_ids"],
              "semantic_equivalence": "attributed_mapping_not_machine_proof", "current_session_permission_inherited": False}
    return effects + [support._new(state, "continuity_map", payload["id"], record)]


def _imported_redirect(entity):
    """Recognize the retained journal's explicit redirect-only frontmatter."""
    if entity["kind"] != "history":
        return None
    body = entity["data"].get("body", "")
    if not isinstance(body, str):
        return None
    header = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", body, re.S)
    if not header or not re.search(r"(?m)^journal_index:\s*false\s*$", header[1]):
        return None
    target = re.search(r"(?m)^redirect_to:\s*([^\n]+)$", header[1])
    if not target:
        return None
    path = target[1].strip().strip("\"'")
    return path if path.startswith(("main/", "docs/")) else posixpath.normpath(posixpath.join(posixpath.dirname(entity["id"]), path))


def _canonical_history(state, locator):
    entity = state["objects"].get(locator)
    if entity and entity["kind"] in HISTORY_KINDS | {"legacy_file"} and not _imported_redirect(entity):
        return {locator}
    return {object_key for object_key, entity in state["objects"].items()
            if entity["kind"] in HISTORY_KINDS and not _imported_redirect(entity)
            and locator in {entity["id"], entity["data"].get("legacy", {}).get("legacy_path")}}


def _history_target(state, locator, seen=None):
    canonical = _canonical_history(state, locator)
    if canonical:
        require(len(canonical) == 1, "HISTORY_AMBIGUOUS", "This identity names multiple retained originals.")
        return canonical.pop()
    seen = set() if seen is None else seen
    require(locator not in seen, "HISTORY_REDIRECT_CYCLE", "Historical redirect cycle requires explicit reconciliation.")
    seen.add(locator)
    explicit = [data["target_key"] for _, data in support._all(state, "history_redirect") if data["locator"] == locator]
    if explicit:
        require(len(set(explicit)) == 1, "HISTORY_AMBIGUOUS", "The old locator has conflicting explicit targets.")
        return _history_target(state, explicit[0], seen)
    candidates = set()
    for object_key, entity in state["objects"].items():
        data = entity["data"]
        redirect = _imported_redirect(entity)
        if redirect and locator in {object_key, entity["id"], data.get("legacy", {}).get("legacy_path")}:
            candidates.add(_history_target(state, redirect, set(seen)))
        if entity["kind"] == "artifact_identity" and locator in [data.get("canonical_path"), *data.get("redirects", [])]:
            candidates.update(target for target in data.get("target_objects", []) if target in state["objects"] and state["objects"][target]["kind"] in HISTORY_KINDS)
        if entity["kind"] == "legacy_identity" and locator in {entity["id"], data.get("file"), data.get("legacy_id")}:
            target = data.get("canonical_path") or data.get("target_path") or data.get("canonical_id")
            if target:
                candidates.add(_history_target(state, target, set(seen)))
    require(len(candidates) == 1, "HISTORY_UNRESOLVED" if not candidates else "HISTORY_AMBIGUOUS", "History navigation requires one actual retained target.")
    return candidates.pop()


def resolve_history(state, locator):
    """Return the actual retained record, not just an index label."""
    target = _history_target(state, locator)
    entity = state["objects"][target]
    return {"requested": locator, "target_key": target, "redirected": target != locator, "version": entity["version"],
            "kind": entity["kind"], "id": entity["id"], "record": deepcopy(entity["data"])}


def history_index(state):
    """A canonical index with resolvable navigation, excluding redirect entries."""
    locators = set()
    for _, data in support._all(state, "history_redirect"):
        locators.add(data["locator"])
    for _, data in support._all(state, "artifact_identity"):
        locators.update(data.get("redirects", []))
    for identity, data in support._all(state, "legacy_identity"):
        if data.get("canonical_path") or data.get("target_path") or data.get("canonical_id"):
            locators.add(data.get("file", identity))
    for entity in state["objects"].values():
        if _imported_redirect(entity):
            locators.add(entity["id"])
    aliases, unresolved = {}, []
    for locator in sorted(locators):
        try:
            aliases.setdefault(_history_target(state, locator), []).append(locator)
        except DomainError as error:
            unresolved.append({"locator": locator, "code": error.code})
    entries = []
    for object_key, entity in sorted(state["objects"].items()):
        if entity["kind"] not in HISTORY_KINDS or _imported_redirect(entity):
            continue
        data = entity["data"]
        body = data.get("body", data.get("original_body", ""))
        title = data.get("title") or next((line.lstrip("# ") for line in body.splitlines() if line.strip()), entity["id"])
        entries.append({"target_key": object_key, "kind": entity["kind"], "id": entity["id"], "category": data.get("category", entity["kind"]),
                        "title": title, "aliases": aliases.get(object_key, []), "open": {"locator": object_key}, "version": entity["version"]})
    return {"entries": entries, "unresolved_redirects": unresolved, "authority": False, "navigation": "resolve_history(state, entry.open.locator) returns the full original record"}


def plan(state, request):
    payload, action = request.get("payload"), request.get("action")
    actor = _actor(request)
    if action == "continuity.remap":
        return _remap(state, request, payload, actor)
    if action in {"external.relocate", "external.rebind"}:
        return _reference_change(state, request, payload, actor)
    if action == "history.redirect.register":
        fields(payload, "id", "locator", "target_key", "reason")
        require(not _canonical_history(state, payload["locator"]), "HISTORY_CANONICAL_SHADOW", "An alias cannot replace the identity of an existing retained original.")
        target = resolve_history(state, payload["target_key"])
        require(target["target_key"] == payload["target_key"], "HISTORY_REDIRECT_TARGET", "Point directly to a canonical retained object, not another redirect.")
        support._read(state, request, target["kind"], target["id"])
        require(not any(data["locator"] == payload["locator"] for _, data in support._all(state, "history_redirect")), "HISTORY_REDIRECT_EXISTS", "Retain the existing redirect instead of silently replacing it.")
        require(payload["locator"] not in {target["target_key"], target["id"]}, "HISTORY_REDIRECT_TARGET", "A redirect cannot point to itself.")
        return [support._new(state, "history_redirect", payload["id"], {**deepcopy(payload), "actor": actor})]
    raise DomainError("UNKNOWN_ACTION", f"Unknown continuity action: {action}")
