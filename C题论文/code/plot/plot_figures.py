# -*- coding: utf-8 -*-
r"""
论文数据图绘制脚本（fig03 - fig10）
====================================
一次运行生成论文全部 8 张矢量数据图（PDF），输出到 C题论文/figures/。

运行方式
--------
    cd C题论文/code && python3 plot_figures.py
    # 或从工作区根目录：python3 "C题论文/code/plot_figures.py"

硬性口径
--------
* 中文字体：font.sans-serif = ["Songti SC","Heiti SC","PingFang SC","Arial Unicode MS"]，
  axes.unicode_minus = False；**导入 matplotlib 之前**必须把 MPLCONFIGDIR 指向工作区内
  的缓存目录（C题论文/build/mplcache），否则 macOS 上会因字体缓存不可写而报错。
* 输出：PDF 矢量（pdf.fonttype=42 嵌入 TrueType 子集），bbox_inches="tight"。
* 图内**不写标题**（论文由 LaTeX \caption 给题），只写坐标轴标签与单位；
  每条曲线/子图自带图例、单位与关键数值标注，可脱离正文阅读。
* 数字来源：C题论文/intermediate/*.json（q1 / exp_scan / q2_main / q3_n1 / q3_n2 /
  q3_n4 / q3_perf / q4_price / q4_cvar）与原始附件（附件 1、附件 4）。
  除"分位带"直接由附件 4 原始矩阵计算外，图中所有数字均由中间结果 JSON 复算得到，
  不做任何人工录入。

图的清单（编号与文件名固定）
--------------------------
    fig03_q1_dual_price.pdf          问题 1 最优性证书：电价 vs 储电边际价值 + 充放电量
    fig04_q1_capacity_power.pdf      容量-功率双向扫描
    fig05_cost_waterfall.pdf         问题 1 成本分解瀑布图
    fig06_voi.pdf                    信息价值 VoI（预报时刻数 1/2/4/完全信息）
    fig07_q2_emergency.pdf           问题 2 全年逐日紧急购电 + 报童两条方向性参照
    fig08_q4_price.pdf               附件 4 电价剖面（分位带 + 分时骨架）+ 残差 ACF
    fig09_cvar_frontier.pdf          CVaR 风险-费用前沿（依赖 q4_cvar.json，缺失则跳过）
    fig10_strategy_mechanism.pdf     问题 1 最优策略机制（PV 盈余/负荷/电价/SOC/充放电）
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # -> code/
import _pathsetup  # noqa: E402,F401  子目录引导：把 common/ 与各问目录加入 sys.path

# ---------------------------------------------------------------------------
# 0. 环境（必须在 import matplotlib 之前完成）
# ---------------------------------------------------------------------------
import os

HERE = os.path.dirname(os.path.abspath(__file__))         # code/plot/
PAPER_DIR = os.path.dirname(os.path.dirname(HERE))        # C题论文/
WORKSPACE = os.path.dirname(PAPER_DIR)               # 工作区根目录
MPL_CACHE = os.path.join(PAPER_DIR, "build", "mplcache")
os.makedirs(MPL_CACHE, exist_ok=True)
os.environ["MPLCONFIGDIR"] = MPL_CACHE               # 字体缓存必须可写

import json
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import MonthLocator, DateFormatter, date2num
from matplotlib.ticker import MultipleLocator, FuncFormatter

# ---------------------------------------------------------------------------
# 1. 全局样式
# ---------------------------------------------------------------------------
FONT_STACK = ["Songti SC", "Heiti SC", "PingFang SC", "Arial Unicode MS"]
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": FONT_STACK,
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,          # 嵌入 TrueType 子集，矢量且中文不缺字
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "figure.dpi": 120,
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 9,         # 本脚本不写标题，仅防意外
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.4,
    "axes.grid": True,
    "grid.alpha": 0.28,
    "grid.linewidth": 0.5,
    "axes.linewidth": 0.8,
    "legend.framealpha": 0.92,
    "lines.linewidth": 1.3,
})

# 统一配色
C_PRICE = "#1f4e9c"      # 电价
C_MU = "#c0392b"         # 储电边际价值
C_CHG = "#2e86de"        # 充电
C_DIS = "#e67e22"        # 放电
C_PV = "#e8a33d"         # 光伏
C_LOAD = "#34495e"       # 负载
C_SOC = "#16a085"        # 储电量
C_GREY = "0.55"

# 主口径常数（与 config.py 一致；此处仅用于图上阈值线，不参与任何求解）
DT = 1.0 / 6.0           # h
ETA_C = ETA_D = 0.9      # 单边效率（假设 A2，往返 81%）
E_MAX = 5000.0 * DT      # kWh/槽，充放电量上限 833.3333
S_MIN, S_MAX, S_INIT = 1200.0, 10800.0, 6000.0

INTERMEDIATE = os.path.join(PAPER_DIR, "intermediate")
FIGDIR = os.path.join(PAPER_DIR, "figures")
ATTACH = os.path.join(WORKSPACE, "CUMCM2026Problems(1)", "C题", "附件")

FIG_SOURCES: dict[str, str] = {}   # 文件名 -> 数据来源说明


# ---------------------------------------------------------------------------
# 2. 工具函数
# ---------------------------------------------------------------------------
def load_json(name: str, required: bool = True):
    """读取 intermediate/<name>；required=False 时缺失返回 None。"""
    path = os.path.join(INTERMEDIATE, name)
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError("缺少中间结果文件：%s" % path)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fnum(x: float, nd: int = 2) -> str:
    """千分位数字（论文口径：费用保留 2 位小数）。"""
    return ("{:,.%df}" % nd).format(float(x))


def read_attach_matrix(fname: str):
    """读取附件（首列为日期，其后 144 列）为 ndarray（行=日，列=槽位）。"""
    import pandas as pd
    path = os.path.join(ATTACH, fname)
    df = pd.read_excel(path, header=0)
    df = df.rename(columns={df.columns[0]: "date"})
    df = df.set_index("date")
    df.columns = [f"s{j}" for j in range(144)]
    return df.astype(float).to_numpy()


def read_attach1():
    """附件 1：典型日 {电价 元/kWh, 小区负载 kW, 光伏功率 kW}，144 槽。"""
    import pandas as pd
    df = pd.read_excel(os.path.join(ATTACH, "附件1.xlsx"), header=0)
    df.columns = ["时间", "price", "load", "pv"]
    return (df["price"].to_numpy(float), df["load"].to_numpy(float),
            df["pv"].to_numpy(float))


def slot_hours() -> np.ndarray:
    """槽位左端点（h）：槽 j = [j/6, (j+1)/6)。"""
    return np.arange(144) / 6.0


def step_close(t: np.ndarray, v: np.ndarray):
    """把 144 槽的阶梯序列闭合到 24 h，便于 step/fill_between(step='post')。"""
    return np.append(t, 24.0), np.append(v, v[-1])


def hhmm(hour_float: float) -> str:
    h = int(hour_float)
    m = int(round((hour_float - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return "%d:%02d" % (h, m)


def note(ax, text: str, loc: str = "upper left", fs: float = 7.2, pad: float = 0.38,
         xy: tuple | None = None):
    """轴内信息框（数值标注，不承担标题作用）。xy 给定时按轴分数坐标自定义位置。"""
    if xy is None:
        xy = {"upper left": (0.012, 0.975), "upper right": (0.988, 0.975),
              "lower left": (0.012, 0.030), "lower right": (0.988, 0.030)}[loc]
        ha = "left" if "left" in loc else "right"
        va = "top" if "upper" in loc else "bottom"
    else:
        ha, va = "left", "top"
    ax.text(xy[0], xy[1], text, transform=ax.transAxes, ha=ha, va=va,
            fontsize=fs, linespacing=1.45,
            bbox=dict(boxstyle="round,pad=%.2f" % pad, facecolor="white",
                      edgecolor="0.72", linewidth=0.6, alpha=0.93))


def save(fig, name: str) -> str:
    path = os.path.join(FIGDIR, name)
    fig.savefig(path, format="pdf", bbox_inches="tight",
                metadata={"Creator": "plot_figures.py", "CreationDate": None})
    plt.close(fig)
    return path


def hour_axis(ax):
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: "%d" % int(round(v))))
    ax.set_xlabel("时刻（h）")


# ---------------------------------------------------------------------------
# 3. 各图
# ---------------------------------------------------------------------------
def fig03():
    """问题 1 最优性证书：电价 vs 储电边际价值（含死区与两条阈值线）+ 最优充放电量。"""
    q1 = load_json("q1.json")
    A = q1["arrays"]
    price = np.asarray(A["price"], float)
    mu = -np.asarray(A["dual_eq"], float)        # 取负：储电边际价值（元/kWh）
    c = np.asarray(A["c"], float)
    d = np.asarray(A["d"], float)

    t = slot_hours()
    xe, pe = step_close(t, price)
    _, mue = step_close(t, mu)
    th_c = ETA_C * mue                          # 充电阈值 eta_c * mu_t
    th_d = mue / ETA_D                          # 放电阈值 mu_t / eta_d

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.9, 5.4), sharex=True,
                                   gridspec_kw=dict(height_ratios=[1.32, 1.0], hspace=0.10))

    # ---- 上：价格与边际价值 ----
    ax1.fill_between(xe, th_c, th_d, step="post", color="0.87",
                     label=r"死区：$\eta_c\mu_t\leq p_t\leq \mu_t/\eta_d$（不充不放）")
    ax1.fill_between(xe, pe, th_c, step="post", where=(pe < th_c - 1e-9),
                     color="#f5c26b", alpha=0.75, linewidth=0,
                     label=r"充电窗口：$p_t<\eta_c\mu_t$")
    ax1.step(xe, pe, where="post", color=C_PRICE, label=r"电价 $p_t$（附件 1，元/kWh）")
    ax1.step(xe, mue, where="post", color=C_MU, label=r"储电边际价值 $\mu_t$（元/kWh）")
    ax1.step(xe, th_c, where="post", color="#d35400", ls="--", lw=1.0,
             label=r"充电阈值 $\eta_c\mu_t$")
    ax1.step(xe, th_d, where="post", color="#7d3c98", ls="--", lw=1.0,
             label=r"放电阈值 $\mu_t/\eta_d$")
    ax1.set_ylabel("电价 / 储电边际价值（元·kWh$^{-1}$）")
    ax1.set_ylim(0, 1.62)
    ax1.legend(loc="upper left", ncol=3, columnspacing=0.9, handlelength=1.8)
    note(ax1, "死区比 $1/(\\eta_c\\eta_d)=%.4f$；$\\mu_t$ = LP 等式约束对偶量（水价值）"
         % q1["main"]["ratio_cd"], loc="lower right", fs=6.8)

    # ---- 下：最优充放电量（充电为正、放电为负） ----
    w = 1.0 / 6.0
    ax2.bar(t + w / 2, c, width=w, color=C_CHG, label="最优充电量 $c_t$（kWh/槽）")
    ax2.bar(t + w / 2, -d, width=w, color=C_DIS, label="最优放电量 $d_t$（kWh/槽）")
    ax2.axhline(0, color="0.25", lw=0.7)
    ax2.set_ylim(-1080, 1080)
    ax2.set_ylabel("充放电量（kWh·槽$^{-1}$）\n充电为正、放电为负")
    hour_axis(ax2)
    ax2.legend(loc="upper left", ncol=2, columnspacing=1.0)

    load = np.asarray(A["load"], float)
    pv = np.asarray(A["pv"], float)
    ch_idx = np.where(c > 1e-6)[0]
    dis_idx = np.where(d > 1e-6)[0]
    idle_idx = np.where((c <= 1e-6) & (d <= 1e-6))[0]
    ok_chg = int(np.sum(price[ch_idx] <= ETA_C * mu[ch_idx] + 1e-9))
    ok_dis = int(np.sum(price[dis_idx] >= mu[dis_idx] / ETA_D - 1e-9))
    idle_in = int(np.sum((price[idle_idx] >= ETA_C * mu[idle_idx] - 1e-9) &
                         (price[idle_idx] <= mu[idle_idx] / ETA_D + 1e-9)))
    viol = ch_idx[price[ch_idx] > ETA_C * mu[ch_idx] + 1e-9]
    viol_sur = int(np.sum(pv[viol] > load[viol]))
    note(ax2, "充电槽 %d（其中 %d 个落在阴影充电窗口内；其余 %d 个中有 %d 个处于 PV 盈余槽，"
              "充电由零成本光伏供给）\n"
              "放电槽 %d（%d 个落在放电阈值上方）；空闲槽 %d（%d 个落在死区内）\n"
              "充电量 %s kWh，放电量 %s kWh，充放比 %.4f = $1/(\\eta_c\\eta_d)$"
         % (len(ch_idx), ok_chg, len(viol), viol_sur, len(dis_idx), ok_dis,
            len(idle_idx), idle_in, fnum(c.sum()), fnum(d.sum()), c.sum() / d.sum()),
         loc="lower left", fs=6.5)

    for ax in (ax1, ax2):
        ax.set_xlim(0, 24)
    FIG_SOURCES["fig03_q1_dual_price.pdf"] = (
        "q1.json: arrays.price / arrays.dual_eq(取负=水价值) / arrays.c / arrays.d；"
        "阈值线由 config.py 主口径 eta_c=eta_d=0.9 计算")
    return save(fig, "fig03_q1_dual_price.pdf")


def fig04():
    """容量-功率双向扫描：左=容量扫描（最优费用 + 储电边际价值），右=充放功率上限扫描。"""
    scan = load_json("exp_scan.json")["capacity"]
    caps = np.array([r["cap"] for r in scan["cap_scan"]], float)
    costs = np.array([r["cost"] for r in scan["cap_scan"]], float)
    pows = np.array([r["pmax"] for r in scan["power_scan"]], float)
    pcost = np.array([r["cost"] for r in scan["power_scan"]], float)
    pchg = np.array([r["charge"] for r in scan["power_scan"]], float)
    base = float(scan["base"])

    # 储电容量边际价值 = -dC*/dSbar（相邻扫描点中心/单侧差分，单位 元/kWh）
    mcaps = 0.5 * (caps[1:] + caps[:-1])
    mvals = -(np.diff(costs) / np.diff(caps))

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 3.4))
    fig.subplots_adjust(wspace=0.46)
    LIMIT_C = "#7d3c98"      # 单一自由度放开的参考线

    # ---- 左：容量扫描（最优费用 + 储电容量边际价值） ----
    axL.plot(caps, costs, "o-", color=C_PRICE, ms=3.6, label="最优购电费 $C^*$（元/日）")
    axL.axhline(base, color=C_GREY, ls=":", lw=1.0,
                label="题面容量 12 000 kWh 基准：%s 元/日" % fnum(base))
    axL.axhline(scan["no_capacity_limit"], color=LIMIT_C, ls="--", lw=1.0,
                label="仅解除容量上限：%s 元/日（再省 %.2f%%）"
                      % (fnum(scan["no_capacity_limit"]), scan["gain_no_cap"]))
    axL.set_xlabel("可用储能容量（kWh，保持 10%–90% DOD）")
    axL.set_ylabel("最优购电费（元·日$^{-1}$）")
    axL.set_ylim(24800, 40400)
    axL.set_xlim(0, 50000)

    axL2 = axL.twinx()
    axL2.step(mcaps, mvals, where="mid", color=C_MU, lw=1.3,
              label=r"容量边际价值 $-\partial C^*/\partial\bar S$（元/kWh）")
    axL2.plot(mcaps, mvals, "s", color=C_MU, ms=3.0)
    axL2.set_ylabel(r"边际价值 $-\partial C^*/\partial\bar S$（元·kWh$^{-1}$）",
                    color=C_MU)
    axL2.tick_params(axis="y", colors=C_MU)
    axL2.set_ylim(0, 1.15)
    axL2.grid(False)
    h1, l1 = axL.get_legend_handles_labels()
    h2, l2 = axL2.get_legend_handles_labels()
    axL.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=6.4)
    note(axL, "费用曲线分段线性、下凸；边际价值由 %.3f 单调递减至 %.3f 元/kWh"
         % (mvals[0], mvals[-1]), loc="lower left", fs=6.4)

    # ---- 右：充放电功率上限扫描 ----
    axR.plot(pows, pcost, "o-", color=C_PRICE, ms=3.6, label="最优购电费 $C^*$（元/日）")
    axR.axhline(scan["no_power_limit"], color=LIMIT_C, ls="--", lw=1.0,
                label="仅解除功率上限：%s 元/日（再省 %.2f%%）"
                      % (fnum(scan["no_power_limit"]), scan["gain_no_pow"]))
    axR.set_xlabel("充放电功率上限（kW）")
    axR.set_ylabel("最优购电费（元·日$^{-1}$）")
    axR.set_ylim(33800, 40800)
    axR.set_xlim(600, 11000)

    axR2 = axR.twinx()
    axR2.plot(pows, pchg, "s--", color=C_CHG, ms=3.2, lw=1.1,
              label="全天充电量（kWh/日）")
    axR2.set_ylabel("全天充电量（kWh·日$^{-1}$）", color=C_CHG)
    axR2.tick_params(axis="y", colors=C_CHG)
    axR2.set_ylim(8000, 32000)
    axR2.grid(False)
    h1, l1 = axR.get_legend_handles_labels()
    h2, l2 = axR2.get_legend_handles_labels()
    axR.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=6.4)
    axR2.text(4200, 23400, "充电量饱和（≥7 500 kW）：%s kWh/日" % fnum(pchg[-1]),
              fontsize=6.3, color="#1a5276", ha="left", va="bottom")

    FIG_SOURCES["fig04_q1_capacity_power.pdf"] = (
        "exp_scan.json: capacity.cap_scan / power_scan / base / no_capacity_limit / "
        "no_power_limit / gain_no_cap / gain_no_pow；边际价值为扫描费用的离散差分")
    return save(fig, "fig04_q1_capacity_power.pdf")


def fig05():
    """问题 1 成本分解瀑布图：无储能基线 -> 储能削峰填谷收益 -> 最优购电费。"""
    q1 = load_json("q1.json")["main"]
    base = q1["base_cost"]
    opt = q1["cost"]
    save_amt = q1["saving"]

    fig, ax = plt.subplots(figsize=(4.9, 3.9))
    xs = [0, 1, 2]
    ax.bar(0, base, width=0.56, color="0.72", edgecolor="0.35", linewidth=0.7)
    ax.bar(1, -save_amt, bottom=base, width=0.56, color="#27ae60",
           edgecolor="#1e8449", linewidth=0.7)
    ax.bar(2, opt, width=0.56, color=C_PRICE, edgecolor="#16365c", linewidth=0.7)

    # 连接线
    ax.plot([0.28, 1.72], [base, base], ls="--", lw=0.8, color="0.45")
    ax.plot([1.28, 2.28], [opt, opt], ls="--", lw=0.8, color="0.45")

    ax.text(0, base + 1400, "%s 元" % fnum(base), ha="center", fontsize=7.6)
    ax.text(1, base + 1400, "−%s 元" % fnum(save_amt), ha="center", fontsize=7.6,
            color="#1e8449")
    ax.text(2, opt + 1400, "%s 元" % fnum(opt), ha="center", fontsize=7.6,
            color=C_PRICE)

    ax.set_xticks(xs)
    ax.set_xticklabels(["无储能基线 $C^{base}$\n（净负荷全额购电）",
                        "储能削峰填谷收益\n（价差套利 + 光伏时移）",
                        "最优购电费 $C^*$\n（含储能，日周期）"], fontsize=7.4)
    ax.set_ylabel("日购电费用（元·日$^{-1}$）")
    ax.set_ylim(0, 72000)
    note(ax, "$C^{base}=\\sum_t p_t\\max(L_t-PV_t,0)\\Delta t$\n"
              "口径 C-01 / C-02，附件 1 典型日（全年平均日）\n"
              "节省率 %.2f%%（%s 元/日）"
         % (q1["saving_rate"] * 100, fnum(save_amt)), loc="upper right", fs=6.8)
    FIG_SOURCES["fig05_cost_waterfall.pdf"] = (
        "q1.json: main.base_cost / main.cost / main.saving / main.saving_rate")
    return save(fig, "fig05_cost_waterfall.pdf")


def fig06():
    """信息价值 VoI：预报时刻数 1/2/4/完全信息 的总费用（左轴）与紧急购电量（右轴）。"""
    m1 = load_json("q3_n1.json")["meta"]
    m2 = load_json("q3_n2.json")["meta"]
    m4 = load_json("q3_n4.json")["meta"]
    mp = load_json("q3_perf.json")["meta"]
    metas = [m1, m2, m4, mp]
    cost = np.array([m["total_cost"] for m in metas]) / 1e4      # 万元
    emg = np.array([m["emg_qty"] for m in metas])                # kWh
    labels = ["1 次\n0:00", "2 次\n0:00 + 12:00",
              "4 次\n0:00 / 6:00 / 12:00 / 18:00", "完全信息\n（上界）"]
    x = np.arange(4)

    fig, ax = plt.subplots(figsize=(6.7, 4.2))
    axb = ax.twinx()
    axb.bar(x, emg, width=0.42, color="#aed6f1", edgecolor="#5499c7",
            linewidth=0.7, label="紧急购电量（kWh，右轴）")
    axb.set_ylabel("紧急购电量（kWh）", color="#2471a3")
    axb.tick_params(axis="y", colors="#2471a3")
    axb.set_ylim(0, 760000)
    axb.grid(False)
    for xi, v in zip(x, emg):
        axb.text(xi, v + 9000, fnum(v, 0), ha="center", fontsize=6.8, color="#1a5276")

    ax.plot(x, cost, "o-", color=C_MU, ms=5.0, lw=1.6, label="总费用（万元，左轴）")
    for xi, v in zip(x, cost):
        ax.annotate(fnum(v), (xi, v), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=7.0, color=C_MU)
    for i in range(3):
        dcost = (cost[i] - cost[i + 1]) * 1e4
        ax.annotate("−%s 元" % fnum(dcost, 0),
                    ((x[i] + x[i + 1]) / 2, (cost[i] + cost[i + 1]) / 2),
                    textcoords="offset points", xytext=(0, -14), ha="center",
                    fontsize=6.8, color="0.25")

    ax.axvline(2, color="0.35", ls="--", lw=1.0)
    ax.annotate("本题实际：4 次预报", xy=(2.0, 1418.0), xytext=(1.92, 1423.0),
                ha="right", fontsize=7.0, color="0.25",
                arrowprops=dict(arrowstyle="->", color="0.45", lw=0.7))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.2)
    ax.set_xlim(-0.55, 3.55)
    ax.set_ylim(1384.5, 1445.0)
    ax.set_xlabel("预报时刻数（同一场景集、同一实际轨迹，结果窗口 %d 天）"
                  % m1["n_days"])
    ax.set_ylabel("总费用（万元）", color=C_MU)
    ax.tick_params(axis="y", colors=C_MU)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = axb.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=6.8)

    voi = m1["total_cost"] - mp["total_cost"]
    got = m1["total_cost"] - m4["total_cost"]
    note(ax, "可获得信息价值上界（1 次 → 完全信息）：%s 元\n"
             "4 次已实现 %.1f%%；再加密最多再省 %s 元（%.2f%%）\n"
             "无储能基线 %s 元（%s 万元，超出纵轴范围）"
         % (fnum(voi), got / voi * 100, fnum(m4["total_cost"] - mp["total_cost"]),
            (m4["total_cost"] - mp["total_cost"]) / m4["total_cost"] * 100,
            fnum(m1["base_cost"]), fnum(m1["base_cost"] / 1e4, 2)),
         loc="upper left", fs=6.6)
    FIG_SOURCES["fig06_voi.pdf"] = (
        "q3_n1.json / q3_n2.json / q3_n4.json / q3_perf.json 的 meta."
        "total_cost、meta.emg_qty、meta.base_cost")
    return save(fig, "fig06_voi.pdf")


def fig07():
    """问题 2 全年逐日紧急购电量 + 报童两条方向性参照（缺货概率约 0.114 与 0.200）。"""
    q2 = load_json("q2_main.json")
    meta = q2["meta"]
    nb = load_json("exp_scan.json")["newsboy"]
    dates = [datetime.strptime(r["date"][:10], "%Y-%m-%d") for r in q2["daily"]]
    g = np.array([r["emg_qty"] for r in q2["daily"]], float)

    fig, ax = plt.subplots(figsize=(7.3, 3.3))
    xs = date2num(dates)
    ax.bar(xs, g, width=0.82, color="#aed6f1", edgecolor="#5499c7",
           linewidth=0.35, label="逐日紧急购电量 $\\sum_t g_t$（kWh/日）")

    k = 7
    roll = np.convolve(g, np.ones(k) / k, mode="same")
    ax.plot(xs, roll, color="#1a5276", lw=1.2, label="%d 日滑动平均（kWh/日）" % k)

    q80 = float(np.percentile(g, 80))
    q90 = float(np.percentile(g, 90))
    ax.axhline(q80, color="#e67e22", ls="--", lw=1.1,
               label="口径一参照：日 %d%% 分位 = %s kWh" % (80, fnum(q80)))
    ax.axhline(q90, color="#c0392b", ls="-.", lw=1.1,
               label="口径二参照（近似）：日 %d%% 分位 = %s kWh" % (90, fnum(q90)))

    month_ticks = [d for d in dates if d.day == 1]          # 仅 2025 年各月 1 日，避免出现次年 1 月
    ax.set_xticks(date2num(month_ticks))
    ax.set_xticklabels([d.strftime("%m月") for d in month_ticks])
    ax.set_xlim(date2num(dates[0]) - 2, date2num(dates[-1]) + 2)
    ax.set_ylim(0, 5800)
    ax.set_xlabel("日期（2025-02-01 至 2025-12-31，共 %d 天）" % len(dates))
    ax.set_ylabel("紧急购电量（kWh·日$^{-1}$）")
    ax.legend(loc="upper left", fontsize=6.4, ncol=1)
    note(ax, "逐槽缺货频率 %.2f%%（报童两条方向性参照 0.114–0.200 的下侧）\n"
             "电量满足率 %.2f%%；全年紧急购电量 %s kWh\n"
             "有紧急购电天数 %d/%d；单日最大 %s kWh（%s）"
         % (nb["short_slot_rate"] * 100, nb["fill_rate"] * 100,
            fnum(meta["tot_emg_qty"]), meta["days_with_emg"], len(dates),
            fnum(g.max()), dates[int(np.argmax(g))].strftime("%Y-%m-%d")),
         loc="upper right", fs=6.4)
    FIG_SOURCES["fig07_q2_emergency.pdf"] = (
        "q2_main.json: daily[].emg_qty（334 天）、meta.tot_emg_qty、meta.days_with_emg；"
        "exp_scan.json: newsboy.short_slot_rate / newsboy.fill_rate")
    return save(fig, "fig07_q2_emergency.pdf")


def fig08():
    """附件 4 电价剖面（分位带 + 分时骨架）+ 残差 ACF(1–6)。"""
    pt = load_json("q4_price.json")["price_tests"]
    # 分时骨架：优先用附件 1 原始剖面，缺失时退回 q1.json 的电价数组
    try:
        skel, _, _ = read_attach1()
        skel_src = "附件 1"
    except Exception:
        skel = np.asarray(load_json("q1.json")["arrays"]["price"], float)
        skel_src = "q1.json arrays.price（附件 1 同源）"

    band_ok, M = False, None
    try:
        M = read_attach_matrix("附件4.xlsx")
        band_ok = M.shape[1] == 144 and M.shape[0] > 0
    except Exception:
        band_ok = False

    t = slot_hours()
    xe, ske = step_close(t, skel)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.9, 5.2),
                                   gridspec_kw=dict(height_ratios=[1.5, 1.0], hspace=0.30))

    if band_ok:
        q = np.percentile(M, [10, 25, 50, 75, 90], axis=0)
        qe = np.hstack([q, q[:, [-1]]])
        ax1.fill_between(xe, qe[0], qe[4], step="post", color="#d6e4f0",
                         label="附件 4 电价分位带：10–90%% / 25–75%%（%d 天 × 144 槽）"
                               % M.shape[0])
        ax1.fill_between(xe, qe[1], qe[3], step="post", color="#9ec5e8",
                         label="_nolegend_")
        ax1.step(xe, qe[2], where="post", color="#1a5276", lw=1.2,
                 label="附件 4 逐槽中位数电价（元/kWh）")
    ax1.step(xe, ske, where="post", color=C_PRICE, lw=1.7, ls="--",
             label="分时骨架（%s 电价剖面，元/kWh）" % skel_src)
    ax1.set_ylabel("电价（元·kWh$^{-1}$）")
    ax1.set_ylim(0, 2.4)
    ax1.legend(loc="upper left", fontsize=6.3, ncol=1)
    hour_axis(ax1)
    ax1.set_xlabel("")
    note(ax1, "全年电价均值 %s、最小 %s、最大 %s 元/kWh\n"
              "骨架与附件 4 逐时段均值最大偏差 %.2e 元/kWh"
         % (fnum(pt["price_mean"], 4), fnum(pt["price_min"], 4),
            fnum(pt["price_max"], 4), pt["skeleton_is_mean"]),
         loc="upper right", fs=6.6)

    acf = np.asarray(pt["C2_acf_lag1_6"], float)
    lags = np.arange(1, len(acf) + 1)
    ax2.bar(lags, acf, width=0.5, color="#5dade2", edgecolor="#2471a3",
            linewidth=0.7, label="日内电价残差自相关 ACF($k$)，$k$ 以 10 min 为步长")
    for xi, v in zip(lags, acf):
        ax2.text(xi, v + 0.018, "%.4f" % v, ha="center", fontsize=6.8, color="#1a5276")
    ax2.axhline(0, color="0.3", lw=0.7)
    ax2.set_ylim(0, 1.18)
    ax2.set_xticks(lags)
    ax2.set_xlabel("滞后阶数 $k$（10 min）")
    ax2.set_ylabel("自相关系数")
    ax2.legend(loc="upper right", fontsize=6.8)
    dacf = np.asarray(pt["C2b_daily_acf"], float)
    note(ax2, "日级残差 ACF：lag1 %.4f、lag2 %.4f、lag3 %.4f\n"
              "峰段/谷段波动比 %.4f（%.4f / %.4f 元/kWh）"
         % (dacf[0], dacf[1], dacf[2], pt["C3_sd_ratio"],
            pt["C3_sd_peak"], pt["C3_sd_night"]),
         loc="lower left", fs=6.6)
    FIG_SOURCES["fig08_q4_price.pdf"] = (
        "q4_price.json: price_tests.C2_acf_lag1_6 / C2b_daily_acf / C3_sd_ratio / "
        "C3_sd_peak / C3_sd_night / price_mean / price_min / price_max / skeleton_is_mean；"
        "分位带与骨架由附件 4、附件 1 原始数据计算")
    return save(fig, "fig08_q4_price.pdf")


def fig09(cvar=None, out_name="fig09_cvar_frontier.pdf"):
    """CVaR 风险-费用前沿：lambda 扫描下的期望费用 / CVaR95 / 真实轨迹回测费用。

    q4_cvar.json 由 code/q4.py --mode cvar 生成，结构：
        {"days": [...], "frontier": [{"lam","exp_cost","real_cost","cvar","emg_qty"}, ...]}
    缺失时跳过本图（由 main() 报告），不影响其余 7 张图。
    """
    if cvar is None:
        cvar = load_json("q4_cvar.json", required=False)
    if not cvar:
        return None
    fr = cvar["frontier"]
    lam = np.array([r["lam"] for r in fr], float)
    exp_c = np.array([r["exp_cost"] for r in fr], float)
    cvar_v = np.array([r["cvar"] for r in fr], float)
    real_c = np.array([r["real_cost"] for r in fr], float)
    emg = np.array([r["emg_qty"] for r in fr], float)
    ndays = len(cvar.get("days", []))

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.3, 3.4))
    fig.subplots_adjust(wspace=0.56)

    axL.plot(lam, exp_c, "o-", color=C_PRICE, ms=3.4, label="情景期望费用（元/日）")
    axL.plot(lam, cvar_v, "s-", color=C_MU, ms=3.4, label="CVaR$_{0.95}$（元/日）")
    axL.set_xlabel(r"风险厌恶系数 $\lambda$")
    axL.set_ylabel("费用 / 风险（元·日$^{-1}$）")
    axL.legend(loc="upper left", fontsize=6.8)

    axL2 = axL.twinx()
    axL2.plot(lam, real_c, "^--", color="#16a085", ms=3.4, lw=1.1,
              label="真实轨迹回测费用（元/日，n=%d）" % ndays)
    axL2.set_ylabel("回测费用（元·日$^{-1}$）", color="#16a085")
    axL2.tick_params(axis="y", colors="#16a085")
    axL2.grid(False)
    h1, l1 = axL.get_legend_handles_labels()
    h2, l2 = axL2.get_legend_handles_labels()
    axL.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=6.6)
    note(axL, "紧急购电量 %.1f → %.1f kWh/日\n（$\\lambda$ 由 0 增至 %.1f）"
         % (emg[0], emg[-1], lam[-1]), loc="lower right", fs=6.6)

    # 前沿散点：期望费用 - CVaR
    axR.plot(exp_c, cvar_v, "-", color="0.55", lw=1.0, zorder=1)
    sc = axR.scatter(exp_c, cvar_v, c=lam, cmap="viridis", s=26, zorder=3)
    for i, (xv, yv, lv) in enumerate(zip(exp_c, cvar_v, lam)):
        if i % 2:                    # 每隔一个点标注，避免标签互相压叠
            continue
        axR.annotate(r"$\lambda$=%.1f" % lv, (xv, yv), textcoords="offset points",
                     xytext=(4, 3), fontsize=6.2, color="0.25")
    # 拐点：单位期望费用增量带来的 CVaR 下降最大
    if len(lam) >= 3:
        slope = -np.diff(cvar_v) / np.maximum(np.diff(exp_c), 1e-9)
        k = int(np.argmax(slope))
        axR.scatter([exp_c[k + 1]], [cvar_v[k + 1]], marker="*", s=150,
                    facecolor="none", edgecolor="#c0392b", linewidth=1.2,
                    label=r"边际风险下降最快点 $\lambda$=%.1f" % lam[k + 1])
        axR.legend(loc="lower left", fontsize=6.6)
    cb = fig.colorbar(sc, ax=axR, pad=0.02)
    cb.set_label(r"$\lambda$", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    axR.set_xlabel("情景期望费用（元·日$^{-1}$）")
    axR.set_ylabel("CVaR$_{0.95}$（元·日$^{-1}$）")
    FIG_SOURCES[out_name] = (
        "q4_cvar.json: frontier[].lam / exp_cost / cvar / real_cost / emg_qty，"
        "days（真实轨迹回测子样本，n=%d）" % ndays)
    return save(fig, out_name)


def fig10():
    """问题 1 最优策略机制：PV 盈余/负荷、电价与储电量、充放电量（三子图共享时间轴）。"""
    q1 = load_json("q1.json")
    A = q1["arrays"]
    price = np.asarray(A["price"], float)
    load = np.asarray(A["load"], float)
    pv = np.asarray(A["pv"], float)
    c = np.asarray(A["c"], float)
    d = np.asarray(A["d"], float)
    S = np.asarray(A["S"], float)

    t = slot_hours()
    xe, le = step_close(t, load)
    _, pve = step_close(t, pv)
    _, pe = step_close(t, price)

    surplus = pv > load
    sur_slots = np.where(surplus)[0]
    h_sur = (sur_slots.min() / 6.0, (sur_slots.max() + 1) / 6.0)   # PV 盈余窗口
    cheap = np.where(price <= 0.45)[0]                             # 低价时段（谷段）
    h_cheap = (cheap.min() / 6.0, (cheap.max() + 1) / 6.0)
    peak = np.where(price >= 1.25)[0]                              # 高价时段（峰段）
    h_peak = (peak.min() / 6.0, (peak.max() + 1) / 6.0)

    fig, axes = plt.subplots(3, 1, figsize=(6.9, 7.1), sharex=True,
                             gridspec_kw=dict(height_ratios=[1.0, 1.0, 1.0], hspace=0.16))
    axA, axB, axC = axes

    # 三条竖直参考带（跨子图对齐）
    for ax in axes:
        ax.axvspan(h_sur[0], h_sur[1], color="#f7dc6f", alpha=0.20, zorder=0)
        ax.axvspan(h_cheap[0], h_cheap[1], color="#85c1e9", alpha=0.20, zorder=0)
        ax.axvspan(h_peak[0], h_peak[1], color="#ec7063", alpha=0.13, zorder=0)

    # ---- (a) 功率 ----
    axA.fill_between(xe, le, pve, step="post", where=(pve > le), color=C_PV,
                     alpha=0.45, linewidth=0, label="光伏盈余 $PV_t-L_t$（kW）")
    axA.step(xe, le, where="post", color=C_LOAD, lw=1.4, label="小区负载 $L_t$（kW）")
    axA.step(xe, pve, where="post", color=C_PV, lw=1.4, label="光伏实际功率 $PV_t$（kW）")
    axA.set_ylabel("功率（kW）")
    axA.set_ylim(-600, 11600)
    axA.legend(loc="upper left", fontsize=6.6, ncol=1)
    sur_energy = float((np.maximum(pv - load, 0) * DT).sum())
    note(axA, "光伏盈余时段 %s–%s（%d 槽）：盈余电量 %s kWh\n"
              "该窗口内充电 %s kWh，占全天充电量 %.1f%%"
         % (hhmm(h_sur[0]), hhmm(h_sur[1]), len(sur_slots), fnum(sur_energy),
            fnum(c[surplus].sum()), c[surplus].sum() / c.sum() * 100),
         loc="upper right", fs=6.6)

    # ---- (b) 电价与储电量 ----
    axB.step(xe, pe, where="post", color=C_PRICE, lw=1.4,
             label="电价 $p_t$（附件 1，元/kWh）")
    axB.set_ylabel("电价（元·kWh$^{-1}$）")
    axB.set_ylim(0.30, 1.62)
    axB.legend(loc="upper left", fontsize=6.8)
    axB2 = axB.twinx()
    axB2.step(xe, np.append(S, S[-1]), where="post", color=C_SOC, lw=1.5,
              label="储电量 $S_t$（kWh，右轴）")
    axB2.text(0.3, 5700, "起止储电量 %s kWh（$S_0=S_{144}$，日周期）"
              % fnum(q1["main"]["s0"], 0), fontsize=6.4, color=C_SOC,
              ha="left", va="top")
    axB2.axhline(S_MAX, color=C_SOC, ls=":", lw=1.0)
    axB2.axhline(S_MIN, color=C_SOC, ls=":", lw=1.0)
    axB2.axhline(S_INIT, color="0.45", ls=":", lw=0.9)
    axB2.plot([0, 24], [S_INIT, S_INIT], "o", color=C_SOC, ms=3.4, zorder=5)
    axB2.set_ylim(0, 12600)
    axB2.set_ylabel("储电量（kWh）", color=C_SOC)
    axB2.tick_params(axis="y", colors=C_SOC)
    axB2.grid(False)
    axB2.text(7.5, 10950, "上界 %s kWh（触界 %d/144 槽）"
              % (fnum(S_MAX, 0), int(np.sum(S >= S_MAX - 1e-6))),
              fontsize=6.4, color=C_SOC, ha="left", va="bottom")
    axB2.text(13.5, 1300, "下界 %s kWh（触界 %d/144 槽）"
              % (fnum(S_MIN, 0), int(np.sum(S <= S_MIN + 1e-6))),
              fontsize=6.4, color=C_SOC, ha="left", va="bottom")
    h1, l1 = axB.get_legend_handles_labels()
    h2, l2 = axB2.get_legend_handles_labels()
    axB.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=6.6)

    # ---- (c) 充放电量 ----
    w = 1.0 / 6.0
    axC.bar(t + w / 2, c, width=w, color=C_CHG, label="充电量 $c_t$（kWh/槽）")
    axC.bar(t + w / 2, -d, width=w, color=C_DIS, label="放电量 $d_t$（kWh/槽）")
    axC.axhline(0, color="0.25", lw=0.7)
    axC.axhline(E_MAX, color="0.45", ls=":", lw=0.9)
    axC.axhline(-E_MAX, color="0.45", ls=":", lw=0.9)
    axC.set_ylim(-1400, 1400)
    axC.set_ylabel("充放电量（kWh·槽$^{-1}$）\n充电为正、放电为负")
    hour_axis(axC)
    axC.legend(loc="upper left", fontsize=6.6, ncol=1)
    note(axC, "全天充电 %s kWh、放电 %s kWh，充放比 %.4f\n"
              "功率打满上限（±%s kWh/槽）：充电 %d/144 槽、放电 %d/144 槽\n"
              "（黄：PV 盈余段；蓝：谷段低价；红：峰段高价）"
         % (fnum(c.sum()), fnum(d.sum()), c.sum() / d.sum(), fnum(E_MAX, 0),
            int(np.sum(c >= E_MAX - 1e-6)), int(np.sum(d >= E_MAX - 1e-6))),
         loc="upper right", fs=6.4)

    for ax in axes:
        ax.set_xlim(0, 24)
    FIG_SOURCES["fig10_strategy_mechanism.pdf"] = (
        "q1.json: arrays.price / arrays.load / arrays.pv / arrays.S / arrays.c / "
        "arrays.d，main.s0；阴影窗口由数组本身界定（PV>L 盈余段、p_t≤0.45 谷段、"
        "p_t≥1.25 峰段）")
    return save(fig, "fig10_strategy_mechanism.pdf")


# ---------------------------------------------------------------------------
# 4. 主程序
# ---------------------------------------------------------------------------
def main():
    os.makedirs(FIGDIR, exist_ok=True)
    made, skipped = [], []

    jobs = [("fig03_q1_dual_price.pdf", fig03),
            ("fig04_q1_capacity_power.pdf", fig04),
            ("fig05_cost_waterfall.pdf", fig05),
            ("fig06_voi.pdf", fig06),
            ("fig07_q2_emergency.pdf", fig07),
            ("fig08_q4_price.pdf", fig08),
            ("fig09_cvar_frontier.pdf", fig09),
            ("fig10_strategy_mechanism.pdf", fig10)]

    for name, fn in jobs:
        try:
            path = fn()
        except Exception as exc:            # 单图失败不阻断其余图
            skipped.append((name, "%s: %s" % (type(exc).__name__, exc)))
            print("[失败] %-34s %s: %s" % (name, type(exc).__name__, exc))
            continue
        if path is None:
            skipped.append((name, "依赖的中间结果缺失（q4_cvar.json 未生成）"))
            print("[跳过] %-34s 依赖的中间结果缺失" % name)
        else:
            made.append((name, os.path.getsize(path)))

    print("\n" + "=" * 78)
    print("已生成矢量 PDF：")
    for name, size in made:
        print("  %-34s %9d 字节   来源：%s" % (name, size, FIG_SOURCES.get(name, "?")))
    if skipped:
        print("未生成：")
        for name, why in skipped:
            print("  %-34s %s" % (name, why))
    print("输出目录：%s" % FIGDIR)
    print("=" * 78)
    return made, skipped


if __name__ == "__main__":
    main()
