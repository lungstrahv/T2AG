#!/usr/bin/env python3
"""Preflight the student-controlled Exercise hint gate.

The gate is deliberately read-only.  It makes the configured boundary and
the required student authorization machine-readable, but it does not claim
to be an unbypassable security boundary.  A product-level response mediator
must consume the non-zero deny result to hard-block an outgoing response.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from t2ag_activity import (
    ActivityContractError,
    frontmatter,
    resolve_activity,
)


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "main/10_student/profile/profile.md"
PROFILE_FIELD = "exercise_hint_gate"
GATE_MODES = {"enabled", "disabled"}
INTENTS = {
    "reasoning_feedback",
    "concept_answer",
    "direction_hint",
    "specified_reference",
    "full_solution",
}
AUTHORIZATIONS = {"none", "direction", "reference", "solution"}
REQUIRED_AUTHORIZATION = {
    "direction_hint": "direction",
    "specified_reference": "reference",
    "full_solution": "solution",
}


class HintGateContractError(ValueError):
    """The configured gate or requested preflight is malformed."""


@dataclass(frozen=True)
class GateDecision:
    decision: str
    gate_mode: str
    intent: str
    authorization: str
    constraints: tuple[str, ...]
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision in {"allow", "defer_to_base_rules"}

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "gate_mode": self.gate_mode,
            "intent": self.intent,
            "authorization": self.authorization,
            "student_controlled": True,
            "base_teaching_rules_remain": True,
            "constraints": list(self.constraints),
            "reason": self.reason,
        }


def evaluate_gate(
    gate_mode: str,
    intent: str,
    authorization: str = "none",
) -> GateDecision:
    """Return the deterministic preflight decision for one response intent."""
    if gate_mode not in GATE_MODES:
        raise HintGateContractError(
            f"{PROFILE_FIELD} must be enabled|disabled, got {gate_mode or 'missing'}"
        )
    if intent not in INTENTS:
        raise HintGateContractError(f"unknown hint-gate intent: {intent}")
    if authorization not in AUTHORIZATIONS:
        raise HintGateContractError(
            f"unknown hint-gate authorization: {authorization}"
        )

    if gate_mode == "disabled":
        return GateDecision(
            decision="defer_to_base_rules",
            gate_mode=gate_mode,
            intent=intent,
            authorization=authorization,
            constraints=(
                "gate_disabled_but_base_zero_hint_rules_remain",
                "do_not_claim_independent_mastery_after_unrequested_help",
            ),
            reason="student disabled the executable hint gate",
        )

    if intent == "reasoning_feedback":
        return GateDecision(
            decision="allow",
            gate_mode=gate_mode,
            intent=intent,
            authorization=authorization,
            constraints=(
                "evaluate_only_student_provided_claims",
                "do_not_introduce_new_solution_objects_subgoals_or_steps",
                "do_not_repair_the_argument_without_explicit_authorization",
            ),
            reason="reasoning feedback is allowed inside the student's expressed route",
        )

    if intent == "concept_answer":
        return GateDecision(
            decision="allow",
            gate_mode=gate_mode,
            intent=intent,
            authorization=authorization,
            constraints=(
                "answer_the_explicitly_requested_concept_only",
                "do_not_apply_the_concept_to_the_active_problem",
                "do_not_introduce_a_problem_specific_subgoal_lemma_or_next_step",
                "return_to_the_exact_pre_question_stop_after_answering",
            ),
            reason="student-initiated concept questions stay isolated from the active proof",
        )

    required = REQUIRED_AUTHORIZATION[intent]
    if authorization != required:
        return GateDecision(
            decision="deny",
            gate_mode=gate_mode,
            intent=intent,
            authorization=authorization,
            constraints=(
                f"require_explicit_student_authorization:{required}",
                "do_not_silently_upgrade_or_downgrade_the_requested_help_level",
            ),
            reason=(
                f"{intent} requires exact student authorization {required}; "
                f"received {authorization}"
            ),
        )
    return GateDecision(
        decision="allow",
        gate_mode=gate_mode,
        intent=intent,
        authorization=authorization,
        constraints=(
            f"stay_within_authorized_help_level:{required}",
            "record_the_authorization_and_highest_help_exposure",
            "do_not_attribute_exposed_steps_to_independent_student_mastery",
        ),
        reason=f"student explicitly authorized {required} help",
    )


def validate_problem_scope(root: Path, course_id: str, problem_id: str) -> dict[str, str]:
    try:
        route = resolve_activity(root, course_id)
    except ActivityContractError as exc:
        raise HintGateContractError("; ".join(exc.errors)) from exc
    if route.activity_type != "exercise":
        raise HintGateContractError(
            f"hint gate requires current Exercise, got {route.activity_type}"
        )
    if not re.fullmatch(rf"{re.escape(route.activity_id)}-Q\d{{3}}", problem_id):
        raise HintGateContractError(
            f"problem is outside current Exercise {route.activity_id}: {problem_id}"
        )
    problems = (
        root
        / "main/40_course"
        / course_id
        / "exercises"
        / route.activity_id
        / "problems.md"
    )
    content = problems.read_text(encoding="utf-8-sig", errors="replace")
    if not re.search(rf"^##\s+{re.escape(problem_id)}\s*$", content, re.MULTILINE):
        raise HintGateContractError(f"unknown ExerciseProblem: {problem_id}")
    return {
        "course_id": course_id,
        "exercise_id": route.activity_id,
        "problem_id": problem_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight one student-controlled Exercise response intent."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--intent", required=True, choices=sorted(INTENTS))
    parser.add_argument(
        "--authorization",
        default="none",
        choices=sorted(AUTHORIZATIONS),
        help="Exact student-authorized help level; default is none.",
    )
    args = parser.parse_args()
    try:
        profile = frontmatter(PROFILE)
        mode = profile.get(PROFILE_FIELD, "")
        scope = validate_problem_scope(ROOT, args.course, args.problem)
        decision = evaluate_gate(mode, args.intent, args.authorization)
    except HintGateContractError as exc:
        print(json.dumps({"decision": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    payload = decision.as_dict()
    payload["scope"] = scope
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if decision.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
