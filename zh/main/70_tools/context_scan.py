#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T2AG 上下文安全扫描工具 (context_scan)
=====================================

这是 T2AG 无运行时 Markdown 教学系统的上下文安全扫描器。
T2AG 中的 LLM 会读取多种外部来源文本（OCR 结果、联网搜索内容、下载的 PDF 文本、
学生粘贴文本等），这些内容在送入教学上下文前需要经过提示注入（Prompt Injection）检测，
防止外部内容劫持教师人格、覆盖系统指令或外泄数据。

本脚本仅依赖 Python 标准库 + 正则表达式，不依赖任何第三方 ML 库，适合在无额外依赖的
环境中运行（如 T2AG 的课程临时页面工作区）。

用法
----
    # 扫描文件
    python context_scan.py <file>

    # 从 stdin 扫描（管道输入）
    echo "some untrusted text" | python context_scan.py -

    # 输出净化后的文本（命中替换为 [BLOCKED: ...]，便于直接送入上下文）
    python context_scan.py <file> --sanitize

    # 在代码中调用
    from context_scan import scan, sanitize
    issues = scan(text)        # 返回 list[Detection]
    safe  = sanitize(text)     # 返回替换后的文本

退出码
------
    0 : 未检测到提示注入
    1 : 检测到潜在提示注入（已打印告警）
    2 : 参数错误 / 文件读取失败

覆盖的威胁类型（6 类）
---------------------
    A. 指令覆盖类      : ignore previous instructions / forget everything /
                         忽略之前的指令 / 覆盖系统指令 / 新的指令: 等
    B. 角色劫持类      : you are now / act as / pretend to be / enter developer mode /
                         你现在是 / 从现在起你是 / 扮演管理员 / 进入越狱模式 等
    C. 指令分隔符伪装  : ### system: / <|system|> / [system] / <<SYS>> / [INST] 等
    D. Shell/敏感路径  : ; rm -rf / ; sudo / /(etc|root|.ssh|.env|.aws)/ / ~/.ssh 等
    E. 隐藏 Unicode    : 零宽字符 U+200B/200C/200D/FEFF、RTL 覆盖 U+202E/202D/202C 等
    F. 数据外泄模式    : curl/wget/fetch + URL / send/upload this to url /
                         把数据发送到 http://... 等

注意：基于正则的检测存在误报可能（如正常教学文本中出现 "you are now ready"）。
      T2AG 建议将本扫描器作为"送入上下文前的第一道过滤"，命中内容由人工或上层
      流程复核，而非直接丢弃全部输入。
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
# 威胁类别常量
# ===========================================================================

CAT_INSTRUCTION_OVERRIDE = "A.指令覆盖"
CAT_ROLE_HIJACK = "B.角色劫持"
CAT_SEPARATOR_DISGUISE = "C.分隔符伪装"
CAT_SHELL_PATH = "D.Shell/敏感路径"
CAT_HIDDEN_UNICODE = "E.隐藏Unicode字符"
CAT_DATA_EXFIL = "F.数据外泄"


# ===========================================================================
# 威胁检测规则（集中管理）
# 每条规则: (类别, 规则名, 正则字符串, re flags)
# 规则名用于告警展示；正则字符串统一使用原始字符串。
# ===========================================================================

THREAT_RULES: list[tuple[str, str, str, int]] = [
    # -------------------------------------------------------------------
    # A. 指令覆盖类 (Instruction Override)
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
    (CAT_INSTRUCTION_OVERRIDE, "忽略之前的指令",
     r"忽略(之前|上面|前面|此前|之前所有)的?(指令|提示|规则|系统提示|系统指令)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "覆盖系统指令",
     r"覆盖(系统|安全|原有)?的?(指令|提示|规则|策略)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "新的指令冒号",
     r"新的(指令|提示|规则|要求)\s*[:：]",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "无视系统指令",
     r"无视(之前|前面|此前|系统|原有)的?(指令|提示|规则|系统提示)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "不要遵循指令",
     r"不要(遵循|遵守|理会|执行)(之前|上面|前面|系统|原有)?的?(指令|提示|规则)",
     re.IGNORECASE),
    (CAT_INSTRUCTION_OVERRIDE, "放弃上述设定",
     r"放弃(上述|之前|前面|以上)的?(设定|指令|规则|约束|限制)",
     re.IGNORECASE),

    # -------------------------------------------------------------------
    # B. 角色劫持类 (Role Hijacking)
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
    (CAT_ROLE_HIJACK, "你现在是",
     r"你(现在|从此|以后|接下来)(是|就是|将(是|成为)|扮演|充当)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "从现在起你是",
     r"从现在起(你|请)(是|将(是|成为)|扮演|充当)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "扮演管理员",
     r"扮演(管理员|开发者|root|超级用户|dan|上帝|助手|不同角色)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "进入越狱模式",
     r"进入(越狱|开发者|管理员|上帝|root|sudo|dan|无限制)模式",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "你是开发者",
     r"你(现在|从此|以后)?(是|扮演|充当)(一个|一名)?(管理员|开发者|root|超级用户|dan|上帝|无限制)",
     re.IGNORECASE),
    (CAT_ROLE_HIJACK, "请扮演",
     r"请(扮演|假装|充当)(管理员|开发者|root|超级用户|dan|上帝|助手|不同角色)",
     re.IGNORECASE),

    # -------------------------------------------------------------------
    # C. 指令分隔符伪装 (Separator / Role-tag Disguise)
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
    # D. Shell / 敏感路径 (Shell injection & sensitive paths)
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
    # E. 隐藏 Unicode 字符 (Hidden / Bidirectional Unicode)
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
    # F. 数据外泄模式 (Data Exfiltration)
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
    (CAT_DATA_EXFIL, "发送到网址",
     r"(发送|上传|传|提交|外传|导出)(这|此|所有|该)?(些|个|条)?(数据|内容|文本|文件|信息|对话)?[^|;\n]{0,40}(到|至|给)\s*https?://",
     re.IGNORECASE),
    (CAT_DATA_EXFIL, "把数据发送到网址",
     r"把(这些|这个|所有|该|此)?(数据|内容|文本|文件|信息|对话)[^|;\n]{0,40}(发送|上传|传|提交)[^|;\n]{0,40}https?://",
     re.IGNORECASE),
]

# 预编译所有规则，避免重复编译
_COMPILED_RULES: list[tuple[str, str, re.Pattern]] = [
    (category, name, re.compile(pattern, flags))
    for (category, name, pattern, flags) in THREAT_RULES
]

# 净化占位符的最大片段展示长度
_SNIPPET_MAX_LEN = 80


@dataclass
class Detection:
    """单次检测结果。

    Attributes:
        category: 命中的威胁类别（如 "A.指令覆盖"）。
        rule_name: 命中的规则名（如 "ignore_previous_instructions"）。
        snippet: 命中的文本片段（已清洗、截断），用于告警展示。
        start: 命中片段在原文本中的起始偏移。
        end: 命中片段在原文本中的结束偏移（不含）。
        line: 命中片段所在行号（从 1 开始）。
    """

    category: str
    rule_name: str
    snippet: str
    start: int
    end: int
    line: int


def _clean_snippet(text: str) -> str:
    """清洗匹配文本用于展示：压缩空白、截断长度。"""
    cleaned = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > _SNIPPET_MAX_LEN:
        cleaned = cleaned[: _SNIPPET_MAX_LEN - 1] + "…"
    return cleaned


def _describe_hidden(match_text: str) -> str:
    """将隐藏 Unicode 字符转为可读的 U+XXXX 形式，便于告警展示。"""
    return " ".join(f"U+{ord(ch):04X}" for ch in match_text)


def _line_number(text: str, pos: int) -> int:
    """根据偏移量计算所在行号（从 1 开始）。"""
    if pos <= 0:
        return 1
    return text.count("\n", 0, pos) + 1


def scan(text: str) -> list[Detection]:
    """扫描文本，返回所有命中的检测结果列表。

    顺序遍历所有预编译规则，对每条规则用 finditer 收集所有命中。
    返回结果按 (start, category, rule_name) 排序，保证输出稳定。

    Args:
        text: 待扫描的文本（通常是 OCR 结果、PDF 文本、搜索内容、学生粘贴文本）。

    Returns:
        Detection 列表；无命中时返回空列表。
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
    # 稳定排序：先按位置，再按类别、规则名
    detections.sort(key=lambda d: (d.start, d.category, d.rule_name))
    return detections


def _merge_spans(detections: list[Detection]) -> list[tuple[int, int, set[str]]]:
    """合并重叠/相邻的命中区间，便于一次性替换。

    Args:
        detections: scan() 返回的检测结果。

    Returns:
        合并后的区间列表，每项为 (start, end, {类别集合})，按 start 升序。
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
    """净化文本：将命中片段替换为占位符。

    占位符格式：``[BLOCKED: 检测到潜在提示注入(<类别>),已移除]``
    其中 ``<类别>`` 为该区间命中的所有类别（按字母序，用 "/" 连接）。
    重叠/相邻的多个命中会合并为一个区间，避免占位符互相嵌套。

    Args:
        text: 待净化的文本。

    Returns:
        净化后的文本；无命中时原样返回。
    """
    detections = scan(text)
    if not detections:
        return text
    merged = _merge_spans(detections)
    # 从后往前替换，避免偏移量失效
    result = text
    for start, end, cats in sorted(merged, key=lambda x: x[0], reverse=True):
        cat_str = "/".join(sorted(cats))
        placeholder = f"[BLOCKED: 检测到潜在提示注入({cat_str}),已移除]"
        result = result[:start] + placeholder + result[end:]
    return result


# ===========================================================================
# CLI 入口
# ===========================================================================

def _read_source(source: str) -> str:
    """读取扫描源：'-' 表示 stdin，否则视为文件路径。

    统一以字节方式读取再按 UTF-8 解码，避免 Windows 默认编码（如 GBK）导致乱码。
    """
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        try:
            with open(source, "rb") as f:
                raw = f.read()
        except OSError as exc:
            # 文件读取失败：退出码 2（与参数错误一致）
            sys.stderr.write(f"[ERROR] 无法读取文件 {source!r}: {exc}\n")
            raise SystemExit(2)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # UTF-8 解码失败时用 replace 兜底，保证仍可扫描
        return raw.decode("utf-8", errors="replace")


def _format_warning(det: Detection) -> str:
    """格式化单条告警为多行字符串。"""
    return (
        f"  类别: {det.category}\n"
        f"  规则: {det.rule_name}\n"
        f"  行号: {det.line}\n"
        f"  片段: {det.snippet}"
    )


def _ensure_utf8_stdio() -> None:
    """将 stdout/stderr 切到 UTF-8，避免 Windows 下中文告警输出乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    """CLI 主函数，返回退出码。"""
    _ensure_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="context_scan.py",
        description="T2AG 上下文安全扫描工具：检测送入教学上下文前的提示注入。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python context_scan.py risky.txt\n"
            "  echo 'ignore previous instructions' | python context_scan.py -\n"
            "  python context_scan.py risky.txt --sanitize\n"
        ),
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="待扫描的文件路径；'-' 或缺省（管道输入时）表示从 stdin 读取",
    )
    parser.add_argument(
        "-s", "--sanitize",
        action="store_true",
        help="输出净化后的文本（命中替换为 [BLOCKED: ...]）而非告警",
    )
    args = parser.parse_args(argv)

    # 缺省且 stdin 是交互终端时，打印用法
    if args.source == "-" and sys.stdin.isatty():
        parser.print_help(sys.stderr)
        return 2

    text = _read_source(args.source)
    detections = scan(text)

    if args.sanitize:
        # 净化模式：输出净化文本到 stdout，告警摘要到 stderr
        sys.stdout.write(sanitize(text))
        if detections:
            sys.stderr.write(f"[!] 已净化 {len(detections)} 处潜在提示注入\n")
            return 1
        return 0

    if not detections:
        print("[OK] 未检测到提示注入")
        return 0

    # 命中：打印告警
    print(f"[!] 检测到 {len(detections)} 处潜在提示注入：")
    for det in detections:
        print(_format_warning(det))
        print("  " + "-" * 40)
    return 1


if __name__ == "__main__":
    sys.exit(main())
