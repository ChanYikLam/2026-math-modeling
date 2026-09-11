#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_numbers.py —— 论文数字与数值台账的对拍（数字纪律 D1 的机械检查）
=====================================================================
列出论文 sections/*.tex 中出现、但在 intermediate/paper_numbers.json（数值台账）
里找不到对应来源的"大数"（≥3 位有效数字、且不是年份/日期/章节号/常见常数），供人工核对。

用法：
    python3 tools/check_numbers.py            # 宽松匹配（默认，容差 rtol=5e-4）
    python3 tools/check_numbers.py --strict   # 主结果类改严：rtol=2e-5，超差项单独列出
    python3 tools/check_numbers.py --json     # 机器可读输出（供 check_paper.py 调用）

口径说明
--------
宽松口径的容差 max(1e-4, 5e-4·|v|) 对千万级数字意味着约 ±7 000 元——早期版本因此让
Q3 的 28.78 元口径漂移（相对 2.1e-6）轻松通过。现在两层并存：
  * 宽松口径仍用于"有没有出处"的粗筛（历史行为，便于对照）；
  * `--strict` 把相对容差压到 2e-6（千万级约 ±28 元）——足以报出"口径漂移 2.1e-6"这类问题，
    超差项单独归类为 strict_fail，
    供修订前扫尾；主结果类数字必须至少通过严格口径。
抽取规则（消除历史伪阳性）
  * 先做 LaTeX 归一：`\\,`、`{,}`、`~`、空白、千分位逗号在**同一个数字内部**一律视为空；
  * 若候选数字两侧仍紧邻数字（如 `0.0259` 抽成 `0259`、`1200,10800` 抽成 `120010800`），
    判为抽取碎片并丢弃；
  * 单位/百分号不参与匹配，但按原样打印，便于人工定位。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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
    """LaTeX 数字 -> float；数字内部的 \\, / {,} / ~ / 空格 / 千分位逗号一律去掉。"""
    s = s.replace("\\,", "").replace("{,}", "").replace("~", "").replace(" ", "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalise_tex(body: str) -> str:
    """归一 LaTeX 数字写法，消除"列表被当成一个数"的抽取伪阳性。

    `12\\,000` / `1{,}234` / `3 000`（千分位组）-> `12000` / `1234` / `3000`；
    `[0.114,\\,0.200]`（小数列表）-> 保留分隔，抽成 0.114 与 0.200 两个数；
    `[1200,10\\,800]`（整数列表，其中一项带千分位）-> `1200 10800`。
    判定依据：只有当"分隔符 + 恰好 3 位数字"后面不再是数字时，才按千分位并入同一个数。
    """
    s = body
    for _ in range(3):                                    # 处理 `3\,000\,000` 这类多级千分位
        s = re.sub(r"(?<=\d)(?:\\,|\{~\}|~|\s|\{,|,)(\d{3})(?![\d])", r"\1", s)
    s = s.replace("\\,", " ").replace("{,}", ",").replace("~", " ").replace(",", " ")
    return s


def strip_latex(line: str) -> str:
    return re.sub(r"\\(?:label|ref|eqref|bref|chapref|appref|cite|evid|calref)\{[^}]*\}", "", line)


def candidates(body: str):
    """产出 (raw, value)；跳过常见常数与抽取碎片。"""
    for m in re.finditer(r"\d+(?:\.\d+)?", normalise_tex(body)):
        raw = m.group(0)
        x = norm(raw)
        if x is None or x < 20:                  # 只看 ≥20 的数字
            continue
        if WHITELIST_RE.match(raw):
            continue
        if str(m.group(0)).startswith("0") and len(str(m.group(0)).split(".")[0]) >= 2:
            continue                             # 抽取碎片（如 0.0259 被切出 0259）
        yield raw, x


def build_ledger():
    led = json.load(open(LEDGER, encoding="utf-8"))
    vals: set = set()
    flatten(led, vals)
    extra = set()
    for v in list(vals):
        extra.add(v / 1e4)                       # 万元
        extra.add(v * 100)                       # 比例 -> 百分数
        if v != 0:
            extra.add(1 / v)
    vals |= extra
    vals |= {round(v, 2) for v in list(vals)}
    return vals


def known(x: float, vals, rtol: float, atol: float) -> bool:
    if abs(x) < 1e-9:
        return True
    return any(abs(v - x) <= max(atol, abs(v) * rtol) for v in vals)


def scan(vals, rtol: float, atol: float):
    out = []
    for f in sorted(SECTIONS.glob("*.tex")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            for raw, x in candidates(strip_latex(line)):
                if not known(x, vals, rtol, atol):
                    out.append((str(f.relative_to(ROOT)), i, raw, x))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="论文数字 vs 数值台账对拍")
    ap.add_argument("--strict", action="store_true",
                    help="主结果类改严：rtol=2e-6、atol=0.02（千万级约 ±28 元；可被 --rtol 覆盖）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（机器可读）")
    ap.add_argument("--rtol", type=float, default=None,
                    help="自定义严格档相对容差（隐含 --strict；默认 2e-6）")
    args = ap.parse_args(argv)

    vals = build_ledger()
    loose = scan(vals, rtol=5e-4, atol=1e-4)
    strict_rtol = args.rtol if args.rtol is not None else 2e-6
    strict = scan(vals, rtol=strict_rtol, atol=0.02) if (args.strict or args.rtol) else []
    strict_only = [t for t in strict if t not in loose]

    if args.json:
        print(json.dumps(dict(
            ledger_size=len(vals), loose=len(loose), strict=len(strict),
            strict_fail=[dict(file=f, line=i, raw=r, value=v) for f, i, r, v in strict_only],
        ), ensure_ascii=False, indent=1))
        return 0

    print(f"台账数字条目：{len(vals)}")
    print(f"疑似无出处的数字：{len(loose)} 处（宽松口径 rtol=5e-4）")
    for f, i, raw, x in loose[:200]:
        print(f"  {f}:{i}  「{raw}」 -> {x}")
    if args.strict:
        # 严格档只报"有出处但不够精确"的项（宽松档已报的"无出处"不在此重复）
        print(f"严格口径（rtol={strict_rtol:g}）超差：{len(strict_only)} 处（已排除上面按宽松档报过的无出处项）；"
              f"两档合计 {len(strict)} 处")
        for f, i, raw, x in strict_only[:200]:
            print(f"  {f}:{i}  「{raw}」 -> {x}")
        print("判定：严格口径超差项须逐条核对——主结果类数字不得依赖 5e-4 的宽容量级。"
              "本次即以 2e-6 档校准：把「台账真值 13 932 402.95 / 正文 13 932 431.73」"
              "这类相对 2.1e-6 的口径漂移，从 5e-4 与 2e-5 两档的「漏报」变为「报出」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
