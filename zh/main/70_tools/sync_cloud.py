#!/usr/bin/env python3
"""T2AG cloud 提示词生成器（EV-0021 / ADR-0004：协议/实例分离）。

设计（对应 2026-08-09 三连裁决：路线 B、开源面仅 skeleton、reply_suffix 写机制不写值）：
- `cloud/T2AG_PROJECT_INSTRUCTIONS.txt` 是生成物，不是真相源。
- 协议内容真相源：`main/50_playbook/cloud_instructions_template.md`（parity 覆盖，零实例值）。
- 实例值真相源：`cloud/t2ag_mobile_entry.md` 的五个字段
  （cloud_project_mode / course / teacher_role / teacher_template / reply_suffix）。
- 模板泄漏自检：任何实例值字面出现在模板中即 FAIL——模板与 skeleton 永不含
  句尾防冒充标记的具体值。
- 本工具只读模板与 mobile_entry、只写 instructions；不碰账本、信道存档或 skeleton。
- skeleton / 未实例化仓库（无 mobile_entry）没有可生成对象，check 直接通过。

用法：
  python main/70_tools/sync_cloud.py            # check-only：再生比对，不落盘
  python main/70_tools/sync_cloud.py --write    # 再生并写回 instructions

Doctor 集成：`check_cloud_contract` 调用 `run_checks(root)`，漂移报 FAIL。
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

import operator_result

ROOT = Path(__file__).resolve().parents[2]

TEMPLATE_REL = "main/50_playbook/cloud_instructions_template.md"
ENTRY_REL = "cloud/t2ag_mobile_entry.md"
OUTPUT_REL = "cloud/T2AG_PROJECT_INSTRUCTIONS.txt"
BODY_MARKER = "<!-- T2AG_TEMPLATE_BODY_START -->\n"

INSTANCE_FIELDS = (
    "cloud_project_mode",
    "course",
    "teacher_role",
    "teacher_template",
    "reply_suffix",
)
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")

# 泄漏扫描只覆盖实例识别值。`cloud_project_mode` 是协议模式枚举
# （personal_instance / generic_skeleton），在协议散文中合法出现，不是秘密。
LEAK_FIELDS = ("course", "teacher_role", "teacher_template", "reply_suffix")


class SyncCloudError(RuntimeError):
    pass


def parse_mobile_entry(text: str) -> dict[str, str]:
    """提取实例字段。格式：`- field: value`（容忍 GENERATED 注释块内外）。"""
    values: dict[str, str] = {}
    for field in INSTANCE_FIELDS:
        m = re.search(rf"^-\s*{field}:\s*(\S+)\s*$", text, re.MULTILINE)
        if m:
            values[field] = m.group(1)
    missing = [f for f in INSTANCE_FIELDS if f not in values]
    if missing:
        raise SyncCloudError(f"mobile_entry 缺实例字段：{missing}")
    return values


def template_body(text: str) -> str:
    if BODY_MARKER not in text:
        raise SyncCloudError(f"模板缺生成体标记 {BODY_MARKER.strip()}")
    return text.split(BODY_MARKER, 1)[1]


def leak_scan(template_text: str, values: dict[str, str]) -> list[str]:
    """模板中不得字面出现任何实例值（协议层写机制不写值）。"""
    leaks = []
    for field in LEAK_FIELDS:
        value = values.get(field, "")
        if value and value in template_text:
            leaks.append(f"{field}={value}")
    return leaks


def render(body: str, values: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise SyncCloudError(f"模板占位符无对应实例字段：{{{{{key}}}}}")
        return values[key]

    rendered = PLACEHOLDER_RE.sub(sub, body)
    leftover = PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise SyncCloudError(f"渲染后仍有未解析占位符：{leftover}")
    return rendered


def expected_instructions(root: Path) -> str:
    template_text = (root / TEMPLATE_REL).read_text(encoding="utf-8")
    entry_text = (root / ENTRY_REL).read_text(encoding="utf-8")
    values = parse_mobile_entry(entry_text)
    leaks = leak_scan(template_text, values)
    if leaks:
        raise SyncCloudError(f"模板含实例值泄漏：{leaks}")
    return render(template_body(template_text), values)


def run_checks(root: Path) -> list[tuple[str, str]]:
    """返回 (level, message) 列表；level ∈ FAIL / WARN / INFO。供 doctor 复用。"""
    reports: list[tuple[str, str]] = []
    entry = root / ENTRY_REL
    template = root / TEMPLATE_REL
    output = root / OUTPUT_REL
    if not entry.exists():
        reports.append(("INFO", "sync_cloud: 无 mobile_entry（skeleton/未实例化），无生成对象"))
        return reports
    if not template.exists():
        reports.append(("FAIL", f"sync_cloud: 模板缺失 {TEMPLATE_REL}"))
        return reports
    try:
        expected = expected_instructions(root)
    except SyncCloudError as exc:
        reports.append(("FAIL", f"sync_cloud: {exc}"))
        return reports
    if not output.exists():
        reports.append(("FAIL", f"sync_cloud: 生成物缺失 {OUTPUT_REL}（运行 --write 再生）"))
        return reports
    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        diff = list(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(),
                "expected(template+entry)", "on-disk", lineterm="", n=0,
            )
        )
        head = "; ".join(diff[2:8])
        reports.append(("FAIL", f"sync_cloud: instructions 与模板再生结果漂移（{len(diff)} diff 行）：{head}"))
    else:
        reports.append(("INFO", "sync_cloud: instructions 与模板+mobile_entry 再生一致"))
    return reports


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="再生并写回 instructions")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.write:
        entry = root / ENTRY_REL
        if not entry.exists():
            print("FAIL sync_cloud: 无 mobile_entry，拒绝在 skeleton/未实例化仓库生成")
            return 1
        try:
            expected = expected_instructions(root)
        except SyncCloudError as exc:
            print(f"FAIL sync_cloud: {exc}")
            return 1
        out = root / OUTPUT_REL
        old = out.read_text(encoding="utf-8") if out.exists() else None
        out.write_text(expected, encoding="utf-8")
        print(f"WROTE {OUTPUT_REL} ({'unchanged' if old == expected else 'updated'})")
        return 0

    worst = 0
    for level, message in run_checks(root):
        print(f"{level} {message}")
        if level == "FAIL":
            worst = 1
    return worst


def main(argv: list[str] | None = None) -> int:
    code = _main(argv)
    operator_result.emit_exit(
        tool="sync_cloud",
        operation="cloud_projection_check_or_write",
        exit_code=code,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
