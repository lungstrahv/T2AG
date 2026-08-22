#!/usr/bin/env python3
"""L1 mutation test: a marker gate must track the RULE, not its surface form.

Why this exists
---------------
Many gates prove "rule R is stated in document D" by grepping a literal phrase P
out of D.  P is part of prose, and prose gets re-wrapped, capitalised at the start
of a sentence, bolded, re-spaced and translated.  When P moves and R does not, the
gate fails on a document that satisfies it perfectly -- a false negative that
accuses a correct document.

That is the `carrier_mismatch` family named in `remediation_governance.md` §7, in a
variant that was invisible for as long as the prose was zh-CN: Chinese has no
spaces to wrap on, no letter case, and during the years the text was never
retranslated the surface never moved.  Three real defects of this one shape landed
within a single day of translation work:

1. a marker straddling a line break (wrap);
2. a marker capitalised at the start of a bold run (case);
3. two *detection patterns* edited as though they were display messages
   (`文件` as a table column key, `零命中` as a stale-claim marker).

Fixing each one as it appeared is whack-a-mole: the next surface change (a hyphen
becoming an em dash, "cannot" becoming "must not") breaks it again.  This test
turns the lesson into a gate.  For every registered marker it applies mutations
that preserve meaning and asserts the verdict does NOT change, then removes the
marker entirely and asserts the verdict DOES change.

The second half is the part that matters most.  A gate that always passes is
indistinguishable from a gate that cannot fail, and `doctor_contracts.md` §8.2
already requires every check to own a fixture that triggers it.  Here the fixture
is generated, so the requirement holds for all 100+ markers at once instead of
resting on someone remembering to write one.

Declared limitation (stated rather than hidden, per `remediation_governance.md` §7)
----------------------------------------------------------------------------------
The case-insensitive fallback applies to every registered marker, including ones
that are really machine tokens (`paused`, `cloud_project_mode: generic_skeleton`).
For those, `PAUSED` would satisfy the gate although a strict parser elsewhere would
reject it.  That is a widening, not a hole -- it accepts a spelling no producer in
this system emits -- and it is recorded here rather than silently relied upon.
Narrowing it needs a prose/token distinction in the registry, which is a separate
adjudication.

Run:
    python -B main/70_tools/test_marker_robustness.py
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import t2ag_doctor as doctor  # noqa: E402

# The three named roles live in one module, so there is one definition each.
from marker_assertions import (  # noqa: E402
    FILLER_HEAD,
    FILLER_TAIL,
    carrier_for,
    empty_carrier,
)


def mutate_rewrap(text: str, spelling: str) -> str | None:
    """Break the marker across a line, the way a re-wrapped paragraph would."""
    if " " not in spelling:
        return None
    head, _, tail = spelling.partition(" ")
    return text.replace(spelling, f"{head}\n  {tail}", 1)


def mutate_sentence_case(text: str, spelling: str) -> str | None:
    """Capitalise the marker's first letter, as a sentence or bold run would."""
    match = re.search(r"[A-Za-z]", spelling)
    if not match:
        return None
    index = match.start()
    flipped = spelling[:index] + spelling[index].swapcase() + spelling[index + 1 :]
    if flipped == spelling:
        return None
    return text.replace(spelling, flipped, 1)


def mutate_upper(text: str, spelling: str) -> str | None:
    if not re.search(r"[a-z]", spelling):
        return None
    return text.replace(spelling, spelling.upper(), 1)


def mutate_emphasis(text: str, spelling: str) -> str | None:
    """Wrap the marker in bold, which is how these phrases actually appear."""
    if "**" in spelling:
        return None
    return text.replace(spelling, f"**{spelling}**", 1)


def mutate_emphasis_moved(text: str, spelling: str) -> str | None:
    """Move the emphasis run: the registry pins one asterisk placement, prose picks another.

    Found on the third recurrence: the registry held `applies **only to X**` while the
    prose bolded the whole phrase as `**applies only to X**`.  Same rule, same words,
    different asterisk position -- and only one of them matched.
    """
    if "**" not in spelling:
        return None
    return text.replace(spelling, "**" + spelling.replace("**", "") + "**", 1)


def mutate_blockquoted(text: str, spelling: str) -> str | None:
    """Wrap the marker in a blockquote that wraps mid-phrase.

    The fourth surface property found (2026-08-20): a `>` prefix on every
    continuation line survives whitespace collapsing, because `>` is not whitespace.
    """
    if " " not in spelling:
        return None
    head, _, tail = spelling.partition(" ")
    return text.replace(spelling, f"> {head}\n> {tail}", 1)


def mutate_padded(text: str, spelling: str) -> str | None:
    """Double the internal spacing, as a reflow or a table alignment would."""
    if " " not in spelling:
        return None
    return text.replace(spelling, spelling.replace(" ", "  "), 1)


PRESERVING = (
    ("rewrap", mutate_rewrap),
    ("sentence_case", mutate_sentence_case),
    ("upper", mutate_upper),
    ("emphasis", mutate_emphasis),
    ("emphasis_moved", mutate_emphasis_moved),
    ("blockquoted", mutate_blockquoted),
    ("padded", mutate_padded),
)


# --- L3.5: which call sites may hold a registered marker literal -------------
# Structural, not lexical.  The role a marker plays is read from the CALL it sits
# inside, which the AST gives exactly.  A regex scanner reading surrounding text
# is the very defect this guards against: on 2026-08-20 one classified 4 of 14
# sites and got one wrong, flagging a legitimate meta-assertion as a bypass.
ROLE_RULE_IDENTITY = {
    "assert_states_rule",
    "assert_does_not_state_rule",
    "has_marker",
    "missing_markers",
    "marker_position",
    "marker_offset",
    "marker_spellings",
    "field_line_re",
    "heading_re",
    "marker_alternation",
}
ROLE_TEST_DATA = {"carrier_for"}
TEST_FILES = sorted(TOOLS.glob("test_*.py")) + [TOOLS / "contract_test_support.py"]


def _callee_name(node: ast.AST) -> str:
    func = getattr(node, "func", None)
    return getattr(func, "attr", None) or getattr(func, "id", "") or ""


def _is_registry_meta_assertion(call: ast.Call) -> bool:
    """`case.assertIn(marker, <x>.registry)` -- role 3, asserted against the registry."""
    if _callee_name(call) not in {"assertIn", "assertNotIn"} or len(call.args) < 2:
        return False
    target = call.args[1]
    return isinstance(target, ast.Attribute) and target.attr in {
        "registry",
        "MARKER_VARIANTS",
    }


def marker_literal_bypasses(path: Path, registry) -> list[tuple[int, str, str]]:
    """Every registered-marker literal in `path` that sits outside a named role."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node.value not in registry:
            continue
        # Nearest enclosing Call determines the role.
        cursor: ast.AST | None = parents.get(id(node))
        call: ast.Call | None = None
        while cursor is not None:
            if isinstance(cursor, ast.Call):
                call = cursor
                break
            cursor = parents.get(id(cursor))
        if call is not None:
            name = _callee_name(call)
            if name in ROLE_RULE_IDENTITY or name in ROLE_TEST_DATA:
                continue
            if _is_registry_meta_assertion(call):
                continue
            found.append((node.lineno, node.value, name or "<not a call>"))
        else:
            found.append((node.lineno, node.value, "<no enclosing call>"))
    return found


class MarkerRobustnessTests(unittest.TestCase):
    """Every registered marker must survive meaning-preserving surface change."""

    def setUp(self) -> None:
        self.registry = doctor.MARKER_VARIANTS
        self.assertTrue(self.registry, "MARKER_VARIANTS must not be empty")

    def test_registry_is_non_trivial(self) -> None:
        """Guard the guard: an emptied registry would make every case below vacuous."""
        self.assertGreater(len(self.registry), 50)

    def test_every_spelling_is_found_verbatim(self) -> None:
        """Baseline: without this, the mutation results below mean nothing."""
        for canonical in self.registry:
            for spelling in doctor.marker_spellings(canonical):
                with self.subTest(marker=canonical, spelling=spelling):
                    self.assertTrue(
                        doctor.has_marker(carrier_for(spelling), canonical),
                        msg=f"{canonical!r} not found via its own spelling {spelling!r}",
                    )

    def test_meaning_preserving_mutations_do_not_change_the_verdict(self) -> None:
        """Wrap, case, emphasis and spacing must never turn a PASS into a FAIL."""
        applied = 0
        for canonical in self.registry:
            for spelling in doctor.marker_spellings(canonical):
                base = carrier_for(spelling)
                for name, mutate in PRESERVING:
                    mutated = mutate(base, spelling)
                    if mutated is None or mutated == base:
                        continue
                    applied += 1
                    with self.subTest(marker=canonical, spelling=spelling, mutation=name):
                        self.assertTrue(
                            doctor.has_marker(mutated, canonical),
                            msg=(
                                f"{name} broke {canonical!r}: the rule is still stated, "
                                "so the gate tracked the surface rather than the rule"
                            ),
                        )
        self.assertGreater(applied, 200, "too few mutations exercised to be meaningful")

    def test_removing_the_marker_flips_the_verdict(self) -> None:
        """The gate must be able to FAIL; a check that cannot fire is not a check."""
        empty = empty_carrier()
        for canonical in self.registry:
            with self.subTest(marker=canonical):
                self.assertFalse(
                    doctor.has_marker(empty, canonical),
                    msg=(
                        f"{canonical!r} is reported present in a document that never "
                        "states it -- this gate passes vacuously"
                    ),
                )

    def test_every_matched_literal_lives_in_the_registry(self) -> None:
        """L3: a literal used for matching must be registered, never written inline.

        Before this, bilingual gates were hand-written as inline `(?:状态|Status)`
        alternations at 18 call sites.  The spelling list then lives in 18 places
        instead of one, the marker has no canonical identity, and -- most of all --
        the mutation cases above cannot see it, because they walk MARKER_VARIANTS.
        The gate built to catch surface-tracking defects protected 111 markers and
        none of those 18; 5 of 5 sampled still failed under a case change.

        This case closes the loop: it reads the source, finds every key handed to a
        pattern builder, and fails when one is not registered.  Adding a builder call
        with an unregistered key silently drops that marker's other spellings, which
        is the exact defect this whole mechanism exists to prevent.
        """
        source = (TOOLS / "t2ag_doctor.py").read_text(encoding="utf-8")
        used = set(
            re.findall(
                r'(?:field_line_re|heading_re|marker_alternation)\(\s*"([^"]+)"',
                source,
            )
        )
        self.assertTrue(used, "no pattern-builder call sites found; the scan broke")
        unregistered = sorted(k for k in used if k not in self.registry)
        self.assertEqual(
            unregistered,
            [],
            msg=(
                "pattern builders were handed unregistered keys, so every non-canonical "
                f"spelling of them is silently unmatchable: {unregistered}"
            ),
        )

    def test_field_and_heading_builders_tolerate_real_surface_drift(self) -> None:
        """The built patterns must survive what a real document does to a label."""
        status = doctor.field_line_re("状态", r"([A-Za-z_]+)")
        for line in (
            "- Status: open",
            "- status: open",
            "- STATUS: open",
            "- **Status**: open",
            "-  Status :  open",
            "- 状态：open",
        ):
            with self.subTest(line=line):
                self.assertTrue(status.search(line), msg=f"field label lost: {line!r}")
        self.assertIsNone(
            status.search("- Statuses: open"),
            msg="the label matcher must not match a different label",
        )

        heading = doctor.heading_re("## 已处理会话")
        for line in ("## Processed sessions", "## processed sessions", "### 已处理会话"):
            with self.subTest(line=line):
                self.assertTrue(heading.search(line), msg=f"heading lost: {line!r}")
        self.assertIsNone(heading.search("## Something else"))


    def test_ordering_positions_survive_translation(self) -> None:
        """`marker_position` must find a marker via ANY spelling, not just the canonical.

        Gates that assert document ORDER used raw `content.find(literal)`.  In a
        translated edition every such lookup returns -1, the ordering assertion
        collapses to "missing", and the reported defect is the wrong one.
        """
        canonical = doctor.marker_spellings("### 步骤 3：按 current_activity 恢复主载体")[0]
        self.assertIn(canonical, self.registry, "fixture marker left the registry")
        english = doctor.marker_spellings(canonical)[1]
        for spelling in (canonical, english, f"**{english}**", english.upper()):
            with self.subTest(spelling=spelling):
                self.assertGreaterEqual(
                    doctor.marker_position(carrier_for(spelling), canonical),
                    0,
                    msg=f"ordering lookup lost {spelling!r}",
                )
        empty = empty_carrier()
        self.assertEqual(doctor.marker_position(empty, canonical), -1)


    def test_registered_markers_only_appear_in_named_roles(self) -> None:
        """L3.5: a registered marker literal must sit inside a named role, always.

        A marker plays three roles in a test and they are indistinguishable in
        source: rule identity, test data, and meta-assertion.  `assertIn(X, Y)`
        accepts all three, so the role has to be carried by the callee name --
        otherwise it can only be inferred, and inference is what failed:
        a context heuristic classified 4 of 14 sites and misjudged one of them.

        This case reads the enclosing CALL from the AST, so it reads structure
        rather than surrounding text.
        """
        bypasses: list[str] = []
        for path in TEST_FILES:
            if not path.is_file():
                continue
            for line, marker, callee in marker_literal_bypasses(path, self.registry):
                bypasses.append(f"{path.name}:{line} {marker!r} inside {callee}()")
        self.assertEqual(
            bypasses,
            [],
            msg=(
                "registered marker literals outside a named role -- use "
                "assert_states_rule() for a rule identity, carrier_for() for test "
                "data, or assertIn(marker, self.registry) for a meta-assertion:\n  "
                + "\n  ".join(bypasses)
            ),
        )

    def test_missing_markers_reports_the_canonical_spelling(self) -> None:
        """A finding must name the registry spelling, or it cannot be looked up."""
        canonical = next(iter(self.registry))
        empty = empty_carrier()
        self.assertEqual(doctor.missing_markers(empty, (canonical,)), [canonical])
        present = carrier_for(doctor.marker_spellings(canonical)[-1])
        self.assertEqual(doctor.missing_markers(present, (canonical,)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
