# -*- coding: utf-8 -*-
"""重构回归对拍（只读）：比较重构前（基线快照）与重构后（当前）的**数值**，而非字节。

背景
----
xlsx 由 openpyxl 写出、PDF 由 matplotlib 写出，两者都带时间戳，字节必然不同；
`intermediate/*.json` 里还有大量**计时字段**（`seconds` / `runtime_s` / `t_*` / `single_cut_t` /
`speedup*` / `created`），它们随机器负载浮动，与模型结果无关。
所以判断“重构是否改变了数字”必须逐字段比**值**，并把计时字段单独归类。

用法
----
1. 重构**前**做一次基线快照：`python3 tools/snapshot_baseline.py`（见同目录脚本或下方说明）
2. 重构后重跑 `python3 code/run_all.py --fast`（或全量）
3. `python3 tools/compare_refactor.py`  → 0 = 无数值差异；1 = 存在数值差异

本脚本退出码 0 表示：5 个结果文件逐表逐格一致、全部 JSON 的**全部非计时字段**一致。
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys

import pandas as pd

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(PAPER, "build", "refactor_backup")
NEW = PAPER

# 计时/元信息字段：随机器负载或挂钟时间变化，与模型数值无关
TIMING = re.compile(
    r"(^|/)(created|seconds|runtime_s|elapsed_s?|speedup[a-z_]*|"
    r"(sum_)?t_[a-z_]+|[a-z_]*_t|[a-z_]*runtime[a-z_]*|cpu[a-z_]*|wall[a-z_]*)$"
)
bad: list[str] = []
timing_changed = 0


def same(a, b) -> bool:
    """NaN == NaN 视为相同（JSON 允许 NaN 字面量）。"""
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def walk(a, b, path, rel, sink):
    global timing_changed
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                bad.append(f"{rel} :: {path}/{k} 仅一侧存在")
            else:
                walk(a[k], b[k], f"{path}/{k}", rel, sink)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            bad.append(f"{rel} :: {path} 长度不同 {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]", rel, sink)
    elif not same(a, b):
        if TIMING.search(path):
            timing_changed += 1
        else:
            bad.append(f"{rel} :: {path}\n        旧={a!r}\n        新={b!r}")


def cmp_xlsx(rel):
    a, b = os.path.join(OLD, rel), os.path.join(NEW, rel)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"缺文件 {rel}")
        return
    xa, xb = pd.ExcelFile(a), pd.ExcelFile(b)
    if xa.sheet_names != xb.sheet_names:
        bad.append(f"{rel} 工作表不同：{xa.sheet_names} vs {xb.sheet_names}")
        return
    for sh in xa.sheet_names:
        try:
            pd.testing.assert_frame_equal(xa.parse(sh), xb.parse(sh),
                                          check_exact=True, atol=0, rtol=0)
        except AssertionError as exc:
            bad.append(f"{rel}[{sh}] 值不同：{str(exc).splitlines()[0]}")
    print(f"  xlsx 逐格一致：{rel}（{len(xa.sheet_names)} 表）")


def cmp_json(rel):
    a, b = os.path.join(OLD, rel), os.path.join(NEW, rel)
    if not (os.path.exists(a) and os.path.exists(b)):
        bad.append(f"缺文件 {rel}")
        return
    walk(json.load(open(a)), json.load(open(b)), "", rel, None)
    print(f"  已比：{rel}")


def snapshot() -> None:
    """建立基线快照（重构前调用一次）。"""
    if os.path.exists(OLD):
        shutil.rmtree(OLD)
    for sub in ("results", "intermediate", "figures"):
        shutil.copytree(os.path.join(NEW, sub), os.path.join(OLD, sub))
    print(f"基线快照已写入 {os.path.relpath(OLD, PAPER)}/")


def main():
    if "--snapshot" in sys.argv:
        snapshot()
        return 0
    if not os.path.isdir(OLD):
        print(f"未找到基线快照 {os.path.relpath(OLD, PAPER)}/，请先跑 --snapshot")
        return 2
    print("== 结果文件（逐表逐格）==")
    for f in sorted(os.listdir(os.path.join(NEW, "results"))):
        if f.endswith(".xlsx"):
            cmp_xlsx(os.path.join("results", f))
    print("== 中间结果（逐字段）==")
    for f in sorted(os.listdir(os.path.join(NEW, "intermediate"))):
        if f.endswith(".json"):
            cmp_json(os.path.join("intermediate", f))
    print("== 结论 ==")
    print(f"  计时字段变化（seconds/runtime_s/t_*/speedup/created）：{timing_changed} 处，与本重构无关")
    if bad:
        print(f"  数值差异：{len(bad)} 处")
        for x in bad:
            print("   -", x)
        return 1
    print("  数值差异：0 处 —— 重构未改变任何模型结果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
