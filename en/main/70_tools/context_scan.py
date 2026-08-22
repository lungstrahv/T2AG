#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T2AG context security scanner (context_scan)
============================================

This is the context security scanner for T2AG, a runtime-free Markdown teaching system.
The LLM in T2AG reads text from many external sources (OCR output, web search results,
extracted PDF text, text pasted by the student), and that content must be checked for
prompt injection before it enters the teaching context, so external material cannot
hijack the teacher persona, override system instructions, or exfiltrate data.

This script depends only on the Python standard library and regular expressions -- no
third-party ML library -- so it runs in environments with no extra dependencies (such as
a T2AG course scratch page workspace).

Usage
-----

    # scan a file
    python context_scan.py notes.md

    # scan from stdin (piped input)
    cat notes.md | python context_scan.py -

    # emit sanitized text (hits replaced with [BLOCKED: ...]), ready to feed to a context
    python context_scan.py notes.md --sanitize

    # call it from code
    from context_scan import scan, sanitize
    issues = scan(text)        # returns list[Detection]
    safe  = sanitize(text)     # returns the substituted text

Exit codes
----------

    0 : no prompt injection detected
    1 : potential prompt injection detected (warnings printed)
    2 : bad arguments / file read failure

Threat types covered (6 categories)
-----------------------------------

    A. Instruction override : ignore previous instructions / forget everything /
                              and the Chinese equivalents
    B. Role hijacking       : you are now / act as / pretend to be / enter developer mode /
                              and the Chinese equivalents
    C. Separator disguise   : ### system: / <|system|> / [system] / <<SYS>> / [INST]
    D. Shell / sensitive path : ; rm -rf / ; sudo / /(etc|root|.ssh|.env|.aws)/ / ~/.ssh
    E. Hidden Unicode       : zero-width U+200B/200C/200D/FEFF, RTL overrides U+202E/202D/202C
    F. Data exfiltration    : curl/wget/fetch + URL / send/upload this to url /
                              and the Chinese equivalents

Note: the detection patterns for Chinese-language attacks are deliberately kept in
Chinese. They are what catches a Chinese-language injection, and translating them would
silently remove that protection -- a scanner that only understands the reader's language
is not a scanner.

Regex-based detection can produce false positives (for example "you are now ready" in
ordinary teaching text). T2AG treats this scanner as the first filter before content
enters a context; hits should be reviewed by a person or a higher-level flow rather than
causing the whole input to be discarded.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

__all__ = [
    "Detection",
    "scan",
    "sanitize",
    "THREAT_RULES",
    "CAT_INSTRUCTION_OVERRIDE",
    "CAT_ROLE_HIJACK",
    "CAT_SEPARATOR_DISGUISE",
    "CAT_SHELL_PATH",
    "CAT_HIDDEN_UNICODE",
    "CAT_DATA_EXFIL",
]

# ===========================================================================
# Threat category constants
# ===========================================================================

CAT_INSTRUCTION_OVERRIDE = "A.instruction-override"
CAT_ROLE_HIJACK = "B.role-hijack"
CAT_SEPARATOR_DISGUISE = "C.separator-disguise"
CAT_SHELL_PATH = "D.shell/sensitive-path"
CAT_HIDDEN_UNICODE = "E.hidden-unicode"
CAT_DATA_EXFIL = "F.data-exfiltration"


# ===========================================================================
# Threat detection rules (kept in one place)
# Each rule: (category, rule name, regex string, re flags)
# The rule name is shown in warnings; regex strings are always raw strings.
# Chinese-language patterns stay in Chinese on purpose: they are what detects a
# Chinese-language attack (see the module docstring).
# ===========================================================================

THREAT_RULES: list[tuple[str, str, str, int]] = [
    # -------------------------------------------------------------------
    # A. Instruction override
    # -------------------------------------------------------------------
    (CAT_INSTRUCTION_OVERRIDE, "ignore_previous_instructions",
     r"\bignore\s+(all|previous|prior|above)\s+(instructions?|prompts?|rules?|messages?)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "forget_everything",
     r"\bforget\s+(everything|all|previous|prior|above)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "disregard_system_prompt",
     r"\bdisregard\s+(system\s+(prompt|message)|previous|prior|above|all|the\s+above)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "override_security",
     r"\boverride\s+(security|system|safety|instructions?|rules?|policy|policies)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "new_instructions_colon",
     r"\bnew\s+(instructions?|prompt|rules?|directive)\s*[:：]",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "ignore_above_directive",
     r"\bignore\s+(the\s+)?above\s+(instructions?|prompts?|rules?|directive)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "stop_following_rules",
     r"\bstop\s+(following|obeying|adhering)\s+(the\s+)?(rules|instructions|policy)\b",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "ignore_previous_instructions_zh",
     r"忽略(之前|上面|前面|此前|之前所有)的?(指令|提示|规则|系统提示|系统指令)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "override_system_instructions_zh",
     r"覆盖(系统|安全|原有)?的?(指令|提示|规则|策略)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "new_instructions_colon_zh",
     r"新的(指令|提示|规则|要求)\s*[:：]",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "disregard_system_instructions_zh",
     r"无视(之前|前面|此前|系统|原有)的?(指令|提示|规则|系统提示)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "do_not_follow_instructions_zh",
     r"不要(遵循|遵守|理会|执行)(之前|上面|前面|系统|原有)?的?(指令|提示|规则)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "abandon_above_settings_zh",
     r"放弃(上述|之前|前面|以上)的?(设定|指令|规则|约束|限制)",
     re.IGNORECASE),

    # -------------------------------------------------------------------
    # B. Role hijacking
    # -------------------------------------------------------------------
    (CAT_ROLE_HIJACK, "you_are_now",
     r"\byou\s+are\s+now\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "act_as",
     r"\bact\s+as\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "pretend_to_be",
     r"\bpretend\s+to\s+be\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "enter_developer_mode",
     r"\benter\s+(developer|jailbreak|admin|god|sudo|root|dan)\s+mode\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "from_now_on_you_are",
     r"\bfrom\s+now\s+on\b[^.\n]{0,40}\byou\b\s+(are|will|act|shall)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "play_role_of",
     r"\bplay\s+(the\s+role\s+of|a\s+role)\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "assume_role",
     r"\bassume\s+(the\s+)?(role|identity|persona)\s+of\b",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "you_are_now_zh",
     r"你(现在|从此|以后|接下来)(是|就是|将(是|成为)|扮演|充当)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "from_now_on_you_are_zh",
     r"从现在起(你|请)(是|将(是|成为)|扮演|充当)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "act_as_admin_zh",
     r"扮演(管理员|开发者|root|超级用户|dan|上帝|助手|不同角色)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "enter_jailbreak_mode_zh",
     r"进入(越狱|开发者|管理员|上帝|root|sudo|dan|无限制)模式",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "you_are_developer_zh",
     r"你(现在|从此|以后)?(是|扮演|充当)(一个|一名)?(管理员|开发者|root|超级用户|dan|上帝|无限制)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "please_act_as_zh",
     r"请(扮演|假装|充当)(管理员|开发者|root|超级用户|dan|上帝|助手|不同角色)",
     re.IGNORECASE),

    # -------------------------------------------------------------------
    # C. Separator / role-tag disguise
    # -------------------------------------------------------------------
    (CAT_SEPARATOR_DISGUISE, "hash_role_colon",
     r"#{2,}\s*(system|assistant|user|developer|admin|tool)\s*[:：]",
     re.IGNORECASE),
    (CAT_SEPARATOR_DISGUISE, "bracket_role",
     r"^\s*\[(system|assistant|user|developer|admin|tool)\]",
     re.IGNORECASE | re.MULTILINE),
    (CAT_SEPARATOR_DISGUISE, "pipe_role_pipe",
     r"<\|(system|assistant|user|im_start|im_end|tool)\|>",
     re.IGNORECASE),
    (CAT_SEPARATOR_DISGUISE, "sys_tag",
     r"<<\s*SYS\s*>>|<</\s*SYS\s*>>",
     re.IGNORECASE),
    (CAT_SEPARATOR_DISGUISE, "inst_tag",
     r"\[\s*/?\s*INST\s*\]",
     re.IGNORECASE),
    (CAT_SEPARATOR_DISGUISE, "role_colon_inline",
     r"^\s*(system|assistant|developer)\s*[:：]",
     re.IGNORECASE | re.MULTILINE),

    # -------------------------------------------------------------------
    # D. Shell injection and sensitive paths
    # -------------------------------------------------------------------
    (CAT_SHELL_PATH, "rm_rf",
     r"(;|\||&&|\|\|)?\s*rm\s+-rf\b",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "sudo_injection",
     r"(;|\||&&|\|\|)\s*sudo\b",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "shell_chain_command",
     r"(;|\||&&|\|\|)\s*(cat|cp|mv|rm|chmod|chown|wget|curl|nc|ncat|bash|sh|zsh|python|perl|ruby|dd|mkfs)\b",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "sensitive_path",
     r"/(?:etc|root|\.ssh|\.env|\.aws|\.git|proc|var/log)(?:/|\b)",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "etc_passwd_shadow",
     r"/etc/(passwd|shadow|hosts|sudoers)\b",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "ssh_private_key",
     r"~/\.ssh/|id_rsa|id_ed25519|id_ecdsa|\.pem\b",
     re.IGNORECASE),
    (CAT_SHELL_PATH, "env_secret",
     r"\b(API_KEY|SECRET_KEY|ACCESS_TOKEN|PRIVATE_KEY|AWS_SECRET)\s*=",
     re.IGNORECASE),

    # -------------------------------------------------------------------
    # E. Hidden / bidirectional Unicode
    # -------------------------------------------------------------------
    (CAT_HIDDEN_UNICODE, "zero_width_space", r"\u200B", 0),
    (CAT_HIDDEN_UNICODE, "zero_width_non_joiner", r"\u200C", 0),
    (CAT_HIDDEN_UNICODE, "zero_width_joiner", r"\u200D", 0),
    (CAT_HIDDEN_UNICODE, "bom_zwnbsp", r"\uFEFF", 0),
    (CAT_HIDDEN_UNICODE, "rtl_override", r"\u202E", 0),
    (CAT_HIDDEN_UNICODE, "ltr_override", r"\u202D", 0),
    (CAT_HIDDEN_UNICODE, "pop_directional_format", r"\u202C", 0),
    (CAT_HIDDEN_UNICODE, "word_joiner", r"\u2060", 0),
    (CAT_HIDDEN_UNICODE, "soft_hyphen", r"\u00AD", 0),

    # -------------------------------------------------------------------
    # F. Data exfiltration
    # -------------------------------------------------------------------
    (CAT_DATA_EXFIL, "curl_url",
     r"\bcurl\b[^|;\n]{0,80}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "wget_url",
     r"\bwget\b[^|;\n]{0,80}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "fetch_url",
     r"\bfetch\s*\([^)]{0,120}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "send_to_url",
     r"\b(send|upload|post|exfiltrate|transmit)\b[^|;\n]{0,80}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "send_this_to_url",
     r"\bsend\s+(this|the|all|data|content|file|conversation)\b[^|;\n]{0,60}\bto\b[^|;\n]{0,60}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "upload_this_to_url",
     r"\bupload\s+(this|the|all|data|content|file|conversation)\b[^|;\n]{0,60}\bto\b[^|;\n]{0,60}https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "nc_ip_port",
     r"\b(nc|ncat)\b[^|;\n]{0,40}\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "base64_pipe",
     r"\|\s*base64\s+(-d|--decode)?\b",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "send_to_url_zh",
     r"(发送|上传|传|提交|外传|导出)(这|此|所有|该)?(些|个|条)?(数据|内容|文本|文件|信息|对话)?[^|;\n]{0,40}(到|至|给)\s*https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "send_data_to_url_zh",
     r"把(这些|这个|所有|该|此)?(数据|内容|文本|文件|信息|对话)[^|;\n]{0,40}(发送|上传|传|提交)[^|;\n]{0,40}https?://",
     re.IGNORECASE),
]

# Pre-compile every rule to avoid recompiling
_COMPILED_RULES: list[tuple[str, str, re.Pattern]] = [
    (category, name, re.compile(pattern, flags))
    for (category, name, pattern, flags) in THREAT_RULES
]

# Maximum snippet length shown inside a sanitize placeholder
_SNIPPET_MAX_LEN = 80


@dataclass
class Detection:
    """One detection result.

    Attributes:
        category: the threat category hit (e.g. "A.instruction-override").
        rule_name: the rule that hit (e.g. "ignore_previous_instructions").
        snippet: the matched text (cleaned and truncated) for the warning display.
        start: start offset of the match in the original text.
        end: end offset of the match in the original text (exclusive).
        line: line number of the match (1-based).
    """

    category: str
    rule_name: str
    snippet: str
    start: int
    end: int
    line: int


def _clean_snippet(text: str) -> str:
    """Clean matched text for display: collapse whitespace, truncate."""
    cleaned = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > _SNIPPET_MAX_LEN:
        cleaned = cleaned[: _SNIPPET_MAX_LEN - 1] + "…"
    return cleaned


def _describe_hidden(match_text: str) -> str:
    """Render hidden Unicode characters as readable U+XXXX for the warning display."""
    return " ".join(f"U+{ord(ch):04X}" for ch in match_text)


def _line_number(text: str, pos: int) -> int:
    """Line number for an offset (1-based)."""
    if pos <= 0:
        return 1
    return text.count("\n", 0, pos) + 1


def scan(text: str) -> list[Detection]:
    """Scan text and return every detection.

    Walks every pre-compiled rule in order, collecting all matches with finditer.
    Results are sorted by (start, category, rule_name) so output is stable.

    Args:
        text: the text to scan (usually OCR output, PDF text, search results, or pasted text).

    Returns:
        A list of Detection; empty when nothing matched.
    """
    if not text:
        return []
    detections: list[Detection] = []
    for category, name, pattern in _COMPILED_RULES:
        for m in pattern.finditer(text):
            if category == CAT_HIDDEN_UNICODE:
                snippet = _describe_hidden(m.group(0))
            else:
                snippet = _clean_snippet(m.group(0))
            detections.append(
                Detection(
                    category=category,
                    rule_name=name,
                    snippet=snippet,
                    start=m.start(),
                    end=m.end(),
                    line=_line_number(text, m.start()),
                )
            )
    # Stable sort: position first, then category and rule name
    detections.sort(key=lambda d: (d.start, d.category, d.rule_name))
    return detections


def _merge_spans(detections: list[Detection]) -> list[tuple[int, int, set[str]]]:
    """Merge overlapping or adjacent hit ranges so they can be replaced in one pass.

    Args:
        detections: the results returned by scan().

    Returns:
        Merged ranges as (start, end, {categories}), ascending by start.
    """
    spans = sorted(
        ((d.start, d.end, d.category) for d in detections),
        key=lambda x: (x[0], x[1]),
    )
    merged: list[tuple[int, int, set[str]]] = []
    for start, end, cat in spans:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end, prev_cats = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end), prev_cats | {cat})
        else:
            merged.append((start, end, {cat}))
    return merged


def sanitize(text: str) -> str:
    """Sanitize text by replacing every hit with a placeholder.

    Placeholder format: ``[BLOCKED: potential prompt injection (<categories>), removed]``
    ``<categories>`` lists every category hit in that range, alphabetically, joined by "/".
    Overlapping or adjacent hits merge into one range so placeholders never nest.

    Args:
        text: the text to sanitize.

    Returns:
        The sanitized text; returned unchanged when nothing matched.
    """
    detections = scan(text)
    if not detections:
        return text
    merged = _merge_spans(detections)
    # Replace back to front so offsets stay valid
    result = text
    for start, end, cats in sorted(merged, key=lambda x: x[0], reverse=True):
        cat_str = "/".join(sorted(cats))
        placeholder = f"[BLOCKED: potential prompt injection ({cat_str}), removed]"
        result = result[:start] + placeholder + result[end:]
    return result


# ===========================================================================
# CLI entry point
# ===========================================================================

def _read_source(source: str) -> str:
    """Read the scan source: '-' means stdin, anything else is a file path.

    Always read bytes and decode as UTF-8, so a Windows default codepage (such as GBK)
    cannot mangle the text.
    """
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        try:
            with open(source, "rb") as f:
                raw = f.read()
        except OSError as exc:
            # file read failure: exit code 2 (same as a bad argument)
            sys.stderr.write(f"[ERROR] cannot read file {source!r}: {exc}\n")
            raise SystemExit(2)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # fall back to replace on a UTF-8 decode failure, so scanning still happens
        return raw.decode("utf-8", errors="replace")


def _format_warning(det: Detection) -> str:
    """Format one warning as a multi-line string."""
    return (
        f"  category: {det.category}\n"
        f"  rule:     {det.rule_name}\n"
        f"  line:     {det.line}\n"
        f"  snippet:  {det.snippet}"
    )


def _ensure_utf8_stdio() -> None:
    """Switch stdout/stderr to UTF-8 so non-ASCII warnings survive on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    """CLI main; returns the exit code."""
    _ensure_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="context_scan.py",
        description="T2AG context security scanner: detect prompt injection before content enters a teaching context.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python context_scan.py risky.txt\n"
            "  echo 'ignore previous instructions' | python context_scan.py -\n"
            "  python context_scan.py risky.txt --sanitize\n"
        ),
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="path of the file to scan; '-' or omitted (when piped) reads from stdin",
    )
    parser.add_argument(
        "-s", "--sanitize",
        action="store_true",
        help="emit sanitized text (hits replaced with [BLOCKED: ...]) instead of warnings",
    )
    args = parser.parse_args(argv)

    # with no argument and an interactive stdin, print usage
    if args.source == "-" and sys.stdin.isatty():
        parser.print_help(sys.stderr)
        return 2

    text = _read_source(args.source)
    detections = scan(text)

    if args.sanitize:
        # sanitize mode: sanitized text to stdout, a warning summary to stderr
        sys.stdout.write(sanitize(text))
        if detections:
            sys.stderr.write(f"[!] sanitized {len(detections)} potential prompt injections\n")
            return 1
        return 0

    if not detections:
        print("[OK] no prompt injection detected")
        return 0

    # hits: print warnings
    print(f"[!] detected {len(detections)} potential prompt injections:")
    for det in detections:
        print(_format_warning(det))
        print("  " + "-" * 40)
    return 1


if __name__ == "__main__":
    sys.exit(main())
