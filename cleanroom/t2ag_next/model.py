"""Small, shared semantic helpers. No persistence or implicit authorization."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict:
        return {"ok": False, "code": self.code, "message": self.message, "details": self.details}


def parse_json(raw: str | bytes):
    """Reject ambiguous external facts before choosing any duplicate value."""
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise DomainError("JSON_DUPLICATE_KEY", f"Repeated JSON field: {name}")
            result[name] = value
        return result

    def constant(value):
        raise DomainError("JSON_NONFINITE", f"Nonfinite JSON value: {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as error:
        raise DomainError("JSON_INVALID", "Input is not unambiguous UTF-8 JSON.") from error


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise DomainError(code, message)


def key(kind: str, object_id: str) -> str:
    require(isinstance(kind, str) and bool(kind) and "/" not in kind,
            "INVALID_KIND", "Object kind must be a nonempty name without slashes.")
    require(isinstance(object_id, str) and bool(object_id.strip()),
            "INVALID_ID", "A stable, nonempty object identity is required.")
    return f"{kind}/{object_id}"


def get(state: dict, kind: str, object_id: str, required: bool = True) -> dict | None:
    item = state.get("objects", {}).get(key(kind, object_id))
    if item is None:
        if required:
            raise DomainError("NOT_FOUND", f"Missing {kind}: {object_id}")
        return None
    return deepcopy(item["data"])


def version(state: dict, kind: str, object_id: str) -> int | None:
    item = state.get("objects", {}).get(key(kind, object_id))
    return item["version"] if item is not None else None


def put(kind: str, object_id: str, data: dict) -> dict:
    key(kind, object_id)
    require(isinstance(data, dict), "INVALID_DATA", "Object data must be an object.")
    return {"op": "put", "kind": kind, "id": object_id, "data": deepcopy(data)}


def fields(payload: dict, *names: str) -> None:
    require(isinstance(payload, dict), "INVALID_PAYLOAD", "Payload must be an object.")
    for name in names:
        require(name in payload and payload[name] is not None and payload[name] != "",
                "MISSING_FIELD", f"Required field: {name}")


def require_student(request: dict, exact_text: str | None = None) -> dict:
    actor = request.get("actor", {})
    require(isinstance(actor, dict) and actor.get("role") == "student",
            "STUDENT_DECISION_REQUIRED", "This action needs an attributed student decision.")
    fields(actor, "source", "text")
    require(isinstance(actor["text"], str) and bool(actor["text"].strip()),
            "EMPTY_STUDENT_STATEMENT", "The actual student statement must be retained.")
    if exact_text is not None:
        require(actor["text"] == exact_text, "STATEMENT_MISMATCH",
                "The decision does not match the bound statement.")
    return deepcopy(actor)


def require_student_decision(request: dict, verbs=(), *, error_code="DECISION_CONTRADICTED") -> dict:
    """Retain an attributed formal choice; reject limited clear contradictions.

    This is deliberately not an NLP classifier or host authentication. The
    calling agent/host must interpret actual input; another caller-supplied
    'accept' field would not add trust. Verbs are fixed by the domain owner.
    """
    actor = require_student(request)
    text = actor["text"].strip().casefold().replace("’", "'")
    bare = text.rstrip("。.!！ ")
    require(bare not in {"no", "not now", "cancel", "decline", "refuse", "不要", "不同意", "拒绝", "取消", "暂不"}, error_code, "An explicit refusal cannot authorize this transition.")
    if verbs:
        verb_pattern = "(?:" + "|".join(re.escape(verb.casefold()) for verb in verbs) + ")"
        # A conditional about the system ("if it cannot activate") is not a
        # refusal; an explicit first-person inability cannot authorize action.
        # The caller still interprets intent; only explicit refusal forms add
        # this limited contradiction check.
        negation = r"(?:\bdo\s+not\b|\bdon't\b|\bwon't\b|\bwould\s+not\b|\b(?:i|we)\s+(?:cannot|can't)\b|\bnot\s+yet\b|\bnever\b|\brefuse\b|不要|不能|不可以|不同意|不批准|不确认|不想|暂不|拒绝)"
        require(re.search(negation + r"[^。.!！?？;；\n]{0,60}" + verb_pattern, text) is None,
                error_code, "The retained statement explicitly contradicts the requested transition.")
    actor["decision_basis"] = {"formal_choice": request.get("action"), "authorization": "agent_attributed",
        "host_identity_authenticated": False, "semantic_intent_machine_verified": False,
        "contradiction_guard": "limited_explicit_denials_only"}
    return actor
