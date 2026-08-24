#!/usr/bin/env python3
"""Named entry points for the three roles a registered marker plays in a test.

Why this module exists
----------------------
A registered marker literal can appear in a test file playing three different
roles, and the roles look identical in source:

1. **rule identity** -- "this document states rule R" (must resolve through
   MARKER_VARIANTS, or a translated edition fails a document that states the rule);
2. **test data** -- "here is a carrier containing this spelling" (must NOT resolve
   through the registry; the spelling itself is what is under test);
3. **meta-assertion** -- "this marker is still registered" (asserts against the
   registry, not against any document).

A scanner reading syntax cannot tell them apart, because `assertIn(X, Y)` is a
generic container that accepts all three.  Measured on 2026-08-20: a
context-heuristic classified only 4 of 14 real sites, and got one of those four
wrong -- it flagged `assertIn(canonical, self.registry)` (a legitimate
meta-assertion) as a bypass, because it read the token `assertIn` rather than what
was being asserted.  The scanner committed the same defect it was written to
catch: taking a surface form for a role.

You cannot detect misuse of a *value*; you can only detect misuse of an *API*.
So the correct use of each role gets a name, and the role becomes machine-readable
at the call site instead of being inferred from context afterwards.

This does not remove human judgement.  It relocates it -- from "review every
literal and reconstruct what it was for" to "pick the right helper while writing",
which is the moment the intent is still present, and where a wrong pick is wrong
immediately rather than three months later with nobody left to ask.

Roles and their entry points
----------------------------
    assert_states_rule(case, doc, marker)   # role 1: rule identity (registry-resolved)
    carrier_for(spelling)                   # role 2: test data (verbatim, no registry)
    case.assertIn(marker, case.registry)    # role 3: meta-assertion (against the registry)

Anything else holding a registered marker literal in a test file is a bypass, and
`test_marker_robustness.test_registered_markers_only_appear_in_named_roles`
fails on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import t2ag_doctor as doctor  # noqa: E402

# Filler deliberately holds no word, so no marker in any edition can hide in it and
# make a destructive assertion pass for the wrong reason.
FILLER_HEAD = "---\n0000 1111 2222\n---\n\n"
FILLER_TAIL = "\n\n3333 4444 5555\n"


def carrier_for(spelling: str) -> str:
    """Role 2 -- test data.

    Build a minimal document stating `spelling` once, surrounded by wordless filler.
    The spelling is placed verbatim and is NOT resolved through the registry: what is
    under test here is whether that exact surface is still found.
    """
    return f"{FILLER_HEAD}- {spelling}, and 6666 7777.{FILLER_TAIL}"


def empty_carrier() -> str:
    """A document stating no marker at all, for destructive assertions."""
    return FILLER_HEAD + "- 8888 9999." + FILLER_TAIL


def assert_states_rule(case, document: str, marker: str, *, name: str = "") -> None:
    """Role 1 -- rule identity.

    Assert that `document` states the rule identified by `marker`, in ANY shipped
    language edition.  Always resolves through `doctor.has_marker`, so a translated
    edition satisfying the rule passes, and a document that dropped the rule fails.

    Never write `case.assertIn(marker, document)` for this: that pins one edition's
    spelling and turns a correct translation into a false negative.
    """
    where = name or "the document"
    case.assertTrue(
        doctor.has_marker(document, marker),
        msg=(
            f"{where} no longer states {marker!r} in any registered edition "
            f"(accepted spellings: {doctor.marker_spellings(marker)})"
        ),
    )


def assert_does_not_state_rule(case, document: str, marker: str, *, name: str = "") -> None:
    """Role 1, negative -- the rule must be absent, in every edition."""
    where = name or "the document"
    case.assertFalse(
        doctor.has_marker(document, marker),
        msg=f"{where} unexpectedly states {marker!r}",
    )
