# -*- coding: utf-8 -*-
"""一键复现：依次求解问题 1–4、跑全部横向对照与检验、生成图件，最后做独立审计与数值台账。

用法：python3 run_all.py            （全部，含全部对照实验与图件）
      python3 run_all.py --fast     （仅主链 + 审计 + 台账，跳过对照实验与图件）
预期耗时（单机、arm64、macOS）：主链约 4 分钟（--fast 含审计与台账约 4.4 分钟），
含全部对照与图件约 20 分钟（其中 exp_na / exp_sobol / exp_oos / exp_benchmark 最耗时）。

执行顺序（FINAL 一定最后跑，保证台账反映本次全部输出）：

    STEPS      问题 1--4 + 容量/功率/效率扫描        （--fast 也跑）
    FAST_EXTRA 信息结构对照、K 稳健性、VoI、CVaR 前沿、电价检验
    V2_EXTRA   v2 四组对照、A9/A12 消融、全年单一 LP、非预期性、样本外、Sobol、全部图件
    FINAL      独立审计 audit.py、数值台账 paper_numbers.py

源程序按“每一问一类”组织（各步骤的脚本路径即该结构）：

    code/common/  口径与公共模块      code/q1/ … code/q4/  四问求解脚本
    code/exp/     横向对照与验证脚本   code/plot/           绘图脚本
    code/ 根      入口、独立审计、数值台账、依赖清单

本脚本可用任意工作目录调用（`python3 code/run_all.py`），步骤一律在 code/ 下执行。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("问题 1：典型日确定性 LP", [sys.executable, "q1/q1.py"]),
    ("问题 2：固定价两阶段随机规划（334 天）", [sys.executable, "q2/q2.py", "--tag", "main", "--K", "60", "--scen", "strat", "--info", "R3", "--write"]),
    ("问题 3：多预报时刻滚动优化（四次预报）", [sys.executable, "q3/q3.py", "--epochs", "0,6,12,18", "--tag", "n4", "--K", "60", "--write"]),
    ("问题 4-2：波动电价两阶段", [sys.executable, "q4/q4.py", "--mode", "q42", "--K", "64", "--write"]),
    ("问题 4-3：波动电价滚动优化", [sys.executable, "q4/q4.py", "--mode", "q43", "--K", "64", "--write"]),
    ("容量/功率/效率扫描与报童经验覆盖率", [sys.executable, "exp/exp_scan.py"]),
]
FAST_EXTRA = [
    ("问题 2 对照：完美信息 R1", [sys.executable, "q2/q2.py", "--tag", "cmp_R1", "--K", "60", "--scen", "strat", "--info", "R1"]),
    ("问题 2 对照：典型日预报 R2", [sys.executable, "q2/q2.py", "--tag", "cmp_R2", "--K", "60", "--scen", "strat", "--info", "R2"]),
    ("问题 2 稳健性：K=120", [sys.executable, "q2/q2.py", "--tag", "K120", "--K", "120", "--scen", "strat", "--info", "R3"]),
    ("VoI：1 次预报", [sys.executable, "q3/q3.py", "--epochs", "0", "--tag", "n1", "--K", "60"]),
    ("VoI：2 次预报", [sys.executable, "q3/q3.py", "--epochs", "0,12", "--tag", "n2", "--K", "60"]),
    ("VoI：完全信息上界", [sys.executable, "q3/q3.py", "--epochs", "0,6,12,18", "--tag", "perf", "--K", "60", "--perfect"]),
    ("CVaR 风险—费用前沿", [sys.executable, "q4/q4.py", "--mode", "cvar", "--K", "64", "--step", "6"]),
    ("电价过程检验与情景保真度", [sys.executable, "q4/q4.py", "--mode", "tests", "--K", "64"]),
]
V2_EXTRA = [
    ("v2 相依结构：C 藤 pair-Copula 拟合与生成器样本外对照、分时段 CVaR 风险画像", [sys.executable, "exp/exp_copula.py"]),
    ("v2 对照：机会约束（安全边际分位数扫描与报童互证）", [sys.executable, "exp/exp_chance.py"]),
    ("v2 对照：盒式分布鲁棒（保守度—费用曲线）", [sys.executable, "exp/exp_dro.py"]),
    ("v2 求解工程：L 形（Benders）分解与直接求解对拍", [sys.executable, "exp/decomp.py"]),
    ("假设 A9 量化：负载预报误差敏感性（相对 MAE 0%/5%/10%）", [sys.executable, "exp/exp_loaderr.py"]),
    ("价格信息对照：负载条件化电价预测重加权", [sys.executable, "exp/exp_pricecond.py"]),
    ("假设 A12 消融：实时重调度（电池对已实现值响应的价值）", [sys.executable, "exp/exp_redispatch.py"]),
    ("对照：全年单一 LP 基准（完全信息参照，读 q2_cmp_R1.json）", [sys.executable, "exp/exp_benchmark.py"]),
    ("检验：非预期性（信息泄漏）置换检验", [sys.executable, "exp/exp_na.py"]),
    ("对照：样本外回测（训练窗建情景集、测试窗回放）", [sys.executable, "exp/exp_oos.py"]),
    ("灵敏度：Sobol 全局灵敏度（读 exp_scan.json）", [sys.executable, "exp/exp_sobol.py"]),
    ("图件：图 3–图 10（数据图，每张图一个函数）", [sys.executable, "plot/plot_figures.py"]),
    ("图件：图 11–图 15（v2 新增：相依结构/生成器对照/风险画像/鲁棒前沿/分解）", [sys.executable, "plot/plot_figures_v2.py"]),
]
# 收尾步骤：全部求解与对照跑完后才做审计与台账，保证台账反映的是本次全部输出
FINAL = [
    ("独立审计（AU1–AU10）", [sys.executable, "audit.py"]),
    ("汇总论文数值台账", [sys.executable, "paper_numbers.py"]),
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
    ap.add_argument("--fast", action="store_true", help="跳过对照实验与图件")
    args = ap.parse_args()
    t0 = time.time()
    for name, cmd in STEPS:
        run(name, cmd)
    if not args.fast:
        for name, cmd in FAST_EXTRA:
            run(name, cmd)
        for name, cmd in V2_EXTRA:
            run(name, cmd)
    for name, cmd in FINAL:
        run(name, cmd)
    print("=" * 78)
    print(f"全部完成，总耗时 {time.time()-t0:.1f}s。结果文件在 ../results/，中间结果在 ../intermediate/。")


if __name__ == "__main__":
    main()
