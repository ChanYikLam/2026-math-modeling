# -*- coding: utf-8 -*-
"""一键复现：依次求解问题 1–4、写出结果文件、跑审计与数值台账。

用法：python3 run_all.py            （全部）
      python3 run_all.py --fast     （跳过 K 稳健性与 CVaR 前沿等耗时实验）
预期耗时（单机、arm64、macOS）：约 5 分钟（--fast 约 4 分钟）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("问题 1：典型日确定性 LP", [sys.executable, "q1.py"]),
    ("问题 2：固定价两阶段随机规划（334 天）", [sys.executable, "q2.py", "--tag", "main", "--K", "60", "--scen", "strat", "--info", "R3", "--write"]),
    ("问题 3：多预报时刻滚动优化（四次预报）", [sys.executable, "q3.py", "--epochs", "0,6,12,18", "--tag", "n4", "--K", "60", "--write"]),
    ("问题 4-2：波动电价两阶段", [sys.executable, "q4.py", "--mode", "q42", "--K", "64", "--write"]),
    ("问题 4-3：波动电价滚动优化", [sys.executable, "q4.py", "--mode", "q43", "--K", "64", "--write"]),
    ("容量/功率/效率扫描与报童经验覆盖率", [sys.executable, "exp_scan.py"]),
    ("独立审计（A1–A10）", [sys.executable, "audit.py"]),
    ("汇总论文数值台账", [sys.executable, "paper_numbers.py"]),
]
FAST_EXTRA = [
    ("问题 2 对照：完美信息 R1", [sys.executable, "q2.py", "--tag", "cmp_R1", "--K", "60", "--scen", "strat", "--info", "R1"]),
    ("问题 2 对照：典型日预报 R2", [sys.executable, "q2.py", "--tag", "cmp_R2", "--K", "60", "--scen", "strat", "--info", "R2"]),
    ("问题 2 稳健性：K=120", [sys.executable, "q2.py", "--tag", "K120", "--K", "120", "--scen", "strat", "--info", "R3"]),
    ("VoI：1 次预报", [sys.executable, "q3.py", "--epochs", "0", "--tag", "n1", "--K", "60"]),
    ("VoI：2 次预报", [sys.executable, "q3.py", "--epochs", "0,12", "--tag", "n2", "--K", "60"]),
    ("VoI：完全信息上界", [sys.executable, "q3.py", "--epochs", "0,6,12,18", "--tag", "perf", "--K", "60", "--perfect"]),
    ("CVaR 风险—费用前沿", [sys.executable, "q4.py", "--mode", "cvar", "--K", "64", "--step", "6"]),
    ("电价过程检验与情景保真度", [sys.executable, "q4.py", "--mode", "tests", "--K", "64"]),
]


def run(name, cmd):
    t0 = time.time()
    print("=" * 78)
    print(f"[{name}]  {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=HERE)
    print(f"[{name}] 完成，耗时 {time.time()-t0:.1f}s，退出码 {r.returncode}")
    if r.returncode != 0:
        raise SystemExit(f"步骤失败：{name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="跳过对照实验")
    args = ap.parse_args()
    t0 = time.time()
    for name, cmd in STEPS:
        run(name, cmd)
    if not args.fast:
        for name, cmd in FAST_EXTRA:
            run(name, cmd)
    print("=" * 78)
    print(f"全部完成，总耗时 {time.time()-t0:.1f}s。结果文件在 ../results/，中间结果在 ../intermediate/。")


if __name__ == "__main__":
    main()
