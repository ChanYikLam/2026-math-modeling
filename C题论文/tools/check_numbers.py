#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_numbers.py —— 论文数字与数值台账的对拍（数字纪律 D1 的机械检查）
=====================================================================
列出论文 sections/*.tex 中出现、但在 intermediate/paper_numbers.json（数值台账）
里找不到对应来源的"大数"（≥3 位有效数字、且不是年份/日期/章节号/常见常数），供人工核对。

用法：python3 tools/check_numbers.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "intermediate" / "paper_numbers.json"
SECTIONS = ROOT / "sections"

WHITELIST_RE = re.compile(
    r"^(2025|2026|2024|144|334|365|12000|48000|0\.9|0\.81|0\.5|1\.5|1\.2346|0\.95|0\.8|0\.05|"
    r"1\.0|2\.0|3\.0|4\.0|5\.0|10|100|1000|24|60|36|72|108|12|6|18|15|30|20|50|0\.1|0\.2|0\.3|"
    r"0\.4|0\.6|0\.7|1\.1|1\.2|1\.3|2\.5|7\.5|8400|14400|2500|7500|600|2400|0\.75|0\.85|0\.25)$")


def flatten(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            flatten(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            flatten(v, out)
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in re.findall(r"-?\d+(?:\.\d+)?", obj.replace(",", "").replace(" ", "")):
            try:
                out.add(float(m))
            except ValueError:
                pass


def norm(s: str):
    s = s.replace("\\,", "").replace("{,}", "").replace(" ", "").replace("~", "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    led = json.load(open(LEDGER))
    vals = set()
    flatten(led, vals)
    # 补充派生量：万、百分比、比例
    extra = set()
    for v in list(vals):
        extra.add(v / 1e4)
        extra.add(v * 100)
        if v != 0:
            extra.add(1 / v)
    vals |= extra
    vals |= {round(v, 2) for v in list(vals)}

    def known(x: float) -> bool:
        if abs(x) < 1e-9:
            return True
        for v in vals:
            if abs(v - x) <= max(1e-4, abs(v) * 5e-4):
                return True
        return False

    suspicious = []
    for f in sorted(SECTIONS.glob("*.tex")):
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("%"):
                continue
            body = re.sub(r"\\label\{[^}]*\}", "", line)
            body = re.sub(r"\\ref\{[^}]*\}", "", body)
            body = re.sub(r"\\cite\{[^}]*\}", "", body)
            for m in re.finditer(r"\d[\d\\,\{\}~ ]*\d(?:\.\d+)?", body):
                raw = m.group(0)
                x = norm(raw)
                if x is None or x < 20:            # 只看 ≥20 的数字
                    continue
                if WHITELIST_RE.match(raw.replace(" ", "")):
                    continue
                if not known(x):
                    suspicious.append((str(f.relative_to(ROOT)), i, raw.strip(), x))
    print(f"台账数字条目：{len(vals)}")
    print(f"疑似无出处的数字：{len(suspicious)} 处")
    for f, i, raw, x in suspicious[:200]:
        print(f"  {f}:{i}  「{raw}」 -> {x}")
    return suspicious


if __name__ == "__main__":
    main()
