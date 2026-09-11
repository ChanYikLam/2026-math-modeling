# -*- coding: utf-8 -*-
r"""
v2 新增数据图（fig11 - fig15）
==============================
    fig11_copula_structure.pdf     电价-负载-光伏相依结构：C 藤逐层二元 Copula 与族选择
    fig12_scenario_generators.pdf  四种情景生成器的样本外对照（费用/紧急购电/边际保真度）
    fig13_risk_profile.pdf         分时段 CVaR 风险画像（问题 2 固定价 vs 问题 4 波动价）
    fig14_robust_frontier.pdf      分布鲁棒：保守度—费用曲线（需 exp_dro.json）
    fig15_decomposition.pdf        L 形分解：收敛与规模对照（需 decomp.json）

数字来源：intermediate/exp_copula.json、exp_dro.json、decomp.json 与原始附件，不做人工录入。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import plot_figures as PF          # 复用全局样式（导入时自动设置 MPLCONFIGDIR 与中文字体）
plt = PF.plt

import config as C
import copula as CP
import scen_copula as SC

INTER = PF.INTERMEDIATE
FIG = PF.FIGDIR
C_PRICE, C_LOAD, C_PV = PF.C_PRICE, PF.C_LOAD, PF.C_PV
C_MU, C_CHG, C_DIS, C_SOC, C_GREY = PF.C_MU, PF.C_CHG, PF.C_DIS, PF.C_SOC, PF.C_GREY
FAMILY_CN = {"gaussian": "Gaussian", "t": "t", "clayton": "Clayton",
             "gumbel": "Gumbel", "frank": "Frank"}


def _u(x):
    from scipy import stats
    r = stats.rankdata(np.asarray(x, float))
    return (r - 0.5) / len(x)


def fig11():
    j = PF.load_json("exp_copula.json")
    p1 = j["part1_vine"]
    panel = C.Panel(SC.DATE_ALL)
    dates = pd.date_range(C.WIN_START, C.WIN_END, freq="D")
    lv = SC.daily_levels(panel, dates)
    P = lv["price"].mean(1); L = lv["load"].sum(1) * C.DT; V = lv["pv"].sum(1) * C.DT
    rec = {r["name"]: r for r in p1["vine"]}

    fig = plt.figure(figsize=(7.4, 2.55))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.25], wspace=0.34)

    def contour(ax, u, v, name, tau, col, ttl):
        g = np.linspace(0.002, 0.998, 120)
        U, Vv = np.meshgrid(g, g, indexing="ij")
        r = rec[name]
        d = np.exp(CP.logpdf(r["best"], U, Vv, r["par"]))
        ax.scatter(u, v, s=2.2, c=C_GREY, alpha=0.45, linewidths=0, zorder=1)
        ax.contour(U, Vv, d, levels=6, colors=col, linewidths=0.7, zorder=2)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel("伪观测 $u$（日平均电价）", fontsize=7.6)
        ax.set_ylabel(ttl, fontsize=7.6)
        ax.text(0.03, 0.965, "最优族 %s\n$\\tau=%.3f$，$\\lambda_U=%.3f$\nAIC$=%.1f$"
                % (FAMILY_CN[r["best"]], tau, r["tail"][0], r["aic"]),
                transform=ax.transAxes, va="top", ha="left", fontsize=7.0,
                bbox=dict(fc="white", ec="0.75", lw=0.5, alpha=0.9, pad=1.8))

    ax = fig.add_subplot(gs[0, 0])
    contour(ax, _u(P), _u(L), "T1_price_load", p1["plain"]["tau_price_load"], C_PRICE,
            "$v$（日负载电量，kWh）")
    ax = fig.add_subplot(gs[0, 1])
    contour(ax, _u(P), _u(V), "T1_price_pv", p1["plain"]["tau_price_pv"], C_PV,
            "$v$（日光伏电量，kWh）")
    ax = fig.add_subplot(gs[0, 2])
    pairs = [("T1_price_load", "电价–负载"), ("T1_price_pv", "电价–光伏"),
             ("T2_load_pv|price", "负载–光伏$|$电价")]
    fams = CP.FAMILIES
    w = 0.26
    xs = np.arange(len(fams))
    cols = [C_PRICE, C_PV, C_SOC]
    for i, (nm, lb) in enumerate(pairs):
        r = rec[nm]
        cand = {c["family"]: c["aic"] for c in r["candidates"]}
        vals = [cand.get(f, 0.0) for f in fams]
        ax.bar(xs + (i - 1) * w, vals, width=w, color=cols[i], alpha=0.85, label=lb,
               edgecolor="white", linewidth=0.4)
        best = r["best"]
        k = fams.index(best)
        ax.annotate("*", (xs[k] + (i - 1) * w, cand[best]), ha="center", va="bottom",
                    fontsize=11, color=cols[i])
    ax.set_xticks(xs); ax.set_xticklabels([FAMILY_CN[f] for f in fams], fontsize=7.4)
    ax.set_ylabel("AIC（越小越好）", fontsize=7.6)
    ax.axhline(0, color="0.6", lw=0.6)
    ax.legend(fontsize=6.8, loc="lower left")
    ax.text(0.985, 0.03, "* 为各族中 AIC 最小者", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=6.8, color="0.35")
    PF.save(fig, "fig11_copula_structure.pdf")
    print("fig11 ok")


def fig12():
    j = PF.load_json("exp_copula.json")
    p3 = j["part3_generators"]
    keys = ["hist_strat", "bootstrap", "copula", "scaled"]
    lbl = ["历史代表日", "分块 Bootstrap", "KDE+Copula", "按光伏规模缩放"]
    cols = [C_PRICE, C_GREY, C_MU, C_PV]
    base = p3["hist_strat"]["total_cost"]
    fid = dict(hist_strat=p3["fidelity_hist"], bootstrap=p3["fidelity_boot"],
               copula=p3["fidelity_copula"], scaled=None)
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.45))
    xs = np.arange(len(keys))
    ax = axes[0]
    v = [(p3[k]["total_cost"] / base - 1) * 100 for k in keys]
    b = ax.bar(xs, v, color=cols, alpha=0.88, width=0.6)
    for xi, vi in zip(xs, v):
        ax.annotate("%+.3f%%" % vi, (xi, vi), ha="center",
                    va="bottom" if vi >= 0 else "top", fontsize=7.0,
                    xytext=(0, 2 if vi >= 0 else -2), textcoords="offset points")
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_ylabel("样本外总费用相对差（%）", fontsize=7.6)
    ax.set_xticks(xs); ax.set_xticklabels(lbl, fontsize=6.9, rotation=16, ha="right")
    ax.margins(y=0.30)
    ax.text(0.02, 0.96, "基准：%.0f 元" % base, transform=ax.transAxes, va="top",
            fontsize=6.9, color="0.3")

    ax = axes[1]
    v = [p3[k]["emg_qty"] for k in keys]
    ax.bar(xs, v, color=cols, alpha=0.88, width=0.6)
    for xi, vi in zip(xs, v):
        ax.annotate("%.0f" % vi, (xi, vi), ha="center", va="bottom", fontsize=6.9,
                    xytext=(0, 2), textcoords="offset points")
    ax.set_ylabel("紧急购电量（kWh，184 天累计）", fontsize=7.6)
    ax.set_xticks(xs); ax.set_xticklabels(lbl, fontsize=6.9, rotation=16, ha="right")
    ax.margins(y=0.18)

    ax = axes[2]
    names = ["hist_strat", "bootstrap", "copula"]
    exact = [fid[k]["R_absq_gap"] if fid[k] else np.nan for k in keys[:3]]
    ax.bar(xs[:3], exact, color=cols[:3], alpha=0.88, width=0.55)
    for xi, vi in zip(xs[:3], exact):
        ax.annotate("%.0f" % vi, (xi, vi), ha="center", va="bottom", fontsize=6.9,
                    xytext=(0, 2), textcoords="offset points")
    ax.text(xs[3], 0, "不适用\n（边缘\n保真）", ha="center", va="bottom", fontsize=6.6,
            color="0.4")
    ax.set_ylabel("日残差总量 1%/99% 分位最大绝对偏差（kWh）", fontsize=7.2)
    ax.set_xticks(xs); ax.set_xticklabels(lbl, fontsize=6.9, rotation=16, ha="right")
    ax.margins(y=0.20)
    fig.subplots_adjust(wspace=0.42)
    PF.save(fig, "fig12_scenario_generators.pdf")
    print("fig12 ok")


def fig13():
    j = PF.load_json("exp_copula.json")
    p4 = j["part4_risk"]
    h = np.arange(24)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.5), sharey=False)
    for ax, tag, ttl in ((axes[0], "q2", "问题 2（固定电价）"),
                         (axes[1], "q4", "问题 4-2（波动电价）")):
        mu = np.array(p4[f"{tag}_hour_mean"]); cv = np.array(p4[f"{tag}_hour_cvar"])
        fr = np.array(p4[f"{tag}_hour_shortage_freq"]) * 100
        ax.bar(h, cv, color=C_MU, alpha=0.30, width=0.82, label="逐小时 CVaR$_{0.95}$")
        ax.plot(h, mu, color=C_PRICE, lw=1.5, marker="o", ms=2.4, label="逐小时均值")
        ax.set_xlabel("时刻（h）", fontsize=7.6)
        ax.set_ylabel("费用（元/日）", fontsize=7.6)
        ax.set_xticks(range(0, 24, 3))
        ax2 = ax.twinx()
        ax2.plot(h, fr, color=C_SOC, lw=1.2, ls="--", marker="s", ms=2.2,
                 label="缺电频率")
        ax2.set_ylabel("槽位缺电频率（%）", fontsize=7.4, color=C_SOC)
        ax2.tick_params(axis="y", labelcolor=C_SOC, labelsize=7)
        ax2.grid(False)
        ax.set_title(ttl, fontsize=8.0)
        h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=6.4, loc="upper left", ncol=1)
        pk = int(np.argmax(fr))
        ax2.annotate("峰值 %d:00\n%.1f%%" % (pk, fr[pk]), (pk, fr[pk]), fontsize=6.4,
                     color=C_SOC, xytext=(4, 4), textcoords="offset points")
    fig.subplots_adjust(wspace=0.42)
    PF.save(fig, "fig13_risk_profile.pdf")
    print("fig13 ok")


def fig14():
    j = PF.load_json("exp_dro.json", required=False)
    if not j:
        print("fig14 跳过（缺 exp_dro.json）")
        return
    r0 = j.get("results")
    if isinstance(r0, dict):
        res = [r0[k] for k in sorted(r0, key=lambda s: float(s.split("=")[-1]))]
    elif isinstance(r0, list) and r0 and isinstance(r0[0], dict) and "total_cost" in r0[0]:
        res = r0
    else:
        print("fig14 跳过（exp_dro.json 结构不可用）")
        return
    ks = [r["k"] for r in res]
    tot = [r["total_cost"] for r in res]
    cvar = [r.get("cvar95") for r in res]
    emg = [r["emg_qty"] for r in res]
    fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.5))
    ax[0].plot(ks, np.array(tot) / 1e4, color=C_PRICE, marker="o", ms=3, label="总费用")
    ax[0].set_xlabel("保守度参数 $k$（不确定集半宽，倍标准差）", fontsize=7.6)
    ax[0].set_ylabel("总费用（万元）", fontsize=7.6)
    ax2 = ax[0].twinx()
    if all(v is not None for v in cvar):
        ax2.plot(ks, np.array(cvar) / 1e4, color=C_MU, marker="s", ms=3,
                 label="逐日费用 CVaR$_{0.95}$")
        ax2.set_ylabel("CVaR$_{0.95}$（万元/日）", fontsize=7.4, color=C_MU)
        ax2.tick_params(axis="y", labelcolor=C_MU, labelsize=7)
        ax2.grid(False)
    ax[1].plot(ks, emg, color=C_SOC, marker="o", ms=3)
    ax[1].set_xlabel("保守度参数 $k$", fontsize=7.6)
    ax[1].set_ylabel("紧急购电量（kWh）", fontsize=7.6)
    fig.subplots_adjust(wspace=0.42)
    PF.save(fig, "fig14_robust_frontier.pdf")
    print("fig14 ok")


def fig15():
    j = PF.load_json("decomp.json", required=False)
    if not j or not isinstance(j.get("scenario_scan"), dict):
        print("fig15 跳过（缺 decomp.json 或结构不可用）")
        return
    ent = j["scenario_scan"].get("entries") or []
    if not ent:
        print("fig15 跳过（scenario_scan.entries 为空）")
        return
    Ks, td, tb = [], [], []
    for e in ent:
        rows = e.get("rows") or []
        if not rows:
            continue
        Ks.append(e["K"])
        td.append(sum(r.get("t_direct_total", r.get("t_direct_production", 0.0)) for r in rows))
        tb.append(sum(r.get("t_benders_total", 0.0) for r in rows))
    fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.4))
    ax[0].plot(Ks, td, color=C_PRICE, marker="o", ms=3, label="直接求解（HiGHS）")
    ax[0].plot(Ks, tb, color=C_MU, marker="s", ms=3, label="L 形分解（解析多割）")
    ax[0].set_yscale("log")
    ax[0].set_xlabel("情景数 $K$", fontsize=7.6)
    ax[0].set_ylabel("4 个代表日求解耗时（s，对数轴）", fontsize=7.4)
    ax[0].legend(fontsize=6.6)
    ax[1].plot(Ks, [d / b for d, b in zip(td, tb)], color=C_SOC, marker="^", ms=3.4)
    ax[1].axhline(1.0, color="0.5", lw=0.8, ls="--")
    ax[1].set_xlabel("情景数 $K$", fontsize=7.6)
    ax[1].set_ylabel("加速比（直接求解耗时 / 分解耗时）", fontsize=7.4)
    for k, v in zip(Ks, [d / b for d, b in zip(td, tb)]):
        ax[1].annotate("%.2f×" % v, (k, v), fontsize=6.5, xytext=(0, 3),
                       textcoords="offset points", ha="center")
    ax[1].margins(y=0.22)
    fig.subplots_adjust(wspace=0.4)
    PF.save(fig, "fig15_decomposition.pdf")
    print("fig15 ok")


def main():
    fig11(); fig12(); fig13(); fig14(); fig15()


if __name__ == "__main__":
    main()
