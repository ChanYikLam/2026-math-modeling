# -*- coding: utf-8 -*-
"""
问题 4 的 KDE + Copula 联合场景生成器（v2 新增）
================================================
参考：
  · 崔丽敏等《基于核密度估计和 Copula 函数的风-光-荷联合场景生成》：KDE 拟合边缘分布、
    Copula 刻画相依结构、蒙特卡洛抽样生成联合场景；
  · 宁楠《基于动态 C 藤 pair-Copula 的电力系统动态经济调度》：C 藤逐层二元 Copula、
    以 AIC / 经验 Copula 距离选族；
  · 李翔/孙丰杰：聚类式场景削减（本文件提供分层 medoid 与多初始 K-means 两种削减对照）。

生成对象（与 q4.build_joint_scenarios 输出结构一致）
---------------------------------------------------
  price  (K,144)  情景电价（元/kWh）
  resid  (K,144)  情景预报残差 r_t = (PV^{fcst} - PV^{act}) * DT（kWh）
  w      (K,)     情景权重

"水平 + 形状"分解
-----------------
日水平： P_d = 当日 144 槽电价的均值（元/kWh）；
         R_d = 当日 144 槽预报残差之和（kWh，>0 表示全天高估光伏）。
日内形状：电价形状 = 当日电价剖面 − 当日均值（保留分时骨架与峰谷形态）；
         残差形状 = 当日残差剖面按当日残差之和归一（形状向量 w_{d,t}，Σ_t w=1）。
生成时先由 Copula 抽出 (P, R) 水平对，再在同水平的近邻历史日中抽一个形状贴上，
从而**同时保真水平边际分布、水平间的相依结构与日内形状**。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as C
import copula as CP
import lp_engine as LP

DATE_ALL = pd.date_range(C.WARMUP_START, C.WIN_END, freq="D")


# --------------------------------------------------------------------------
# 日水平与日内形状
# --------------------------------------------------------------------------
def daily_levels(panel, dates):
    """返回 dict(price (n,144), resid (n,144), P (n,), R (n,), load (n,144), pv (n,144))。"""
    p4 = panel.P(volatile=True)
    pv_act = panel.PV()
    load = panel.L()
    idx = [list(DATE_ALL).index(d) for d in dates]
    price = p4.to_numpy(float)[idx]
    pv = pv_act.to_numpy(float)[idx]
    Ld = load.to_numpy(float)[idx]
    resid = np.zeros_like(price)
    for i, d in enumerate(dates):
        fc = panel.pv_forecast(d, 0)
        resid[i] = (fc - pv[i]) * C.DT
    return dict(price=price, resid=resid, pv=pv, load=Ld,
                P=price.mean(1), R=resid.sum(1))


def _shapes(price, resid):
    """电价形状（去日均值）与残差形状（按日总和归一，带下限防除零）。"""
    ps = price - price.mean(1, keepdims=True)
    R = resid.sum(1)
    scale = np.where(np.abs(R) < 1.0, 1.0, R)
    rs = resid / scale[:, None]
    return ps, rs, R


# --------------------------------------------------------------------------
# 水平层 Copula 模型
# --------------------------------------------------------------------------
class LevelCopula:
    """日水平 (P, R) 的 KDE 边缘 + 二元 pair-Copula。"""

    def __init__(self):
        self.mP = None
        self.mR = None
        self.best = None
        self.cands = []

    def fit(self, P, R):
        P = np.asarray(P, float); R = np.asarray(R, float)
        self.mP = CP.KdeMarginal(P)
        self.mR = CP.KdeMarginal(R)
        u = CP.pseudo_obs(P); v = CP.pseudo_obs(R)
        self.u, self.v = u, v
        for fam in CP.FAMILIES:
            try:
                f = CP.fit(fam, u, v)
            except Exception:
                continue
            f["ecdist"] = CP.empirical_copula_distance(fam, u, v, f["par"])
            f["tail"] = CP.tail_dependence(fam, f["par"])
            f["tau_sim"] = self._tau_sim(fam, f["par"])
            self.cands.append(f)
        self.cands.sort(key=lambda d: d["aic"])
        self.best = self.cands[0]
        return self.best

    def _tau_sim(self, fam, par, n=4000, seed=3):
        rng = np.random.default_rng(seed)
        w = rng.random((n, 2)); u = w[:, 0]
        v = np.array([CP.hinv(fam, w[i, 1], u[i], par) for i in range(n)])
        from scipy import stats
        return float(stats.kendalltau(u, v).statistic)

    def sample_levels(self, n, rng):
        """按拟合的最优 Copula 抽 (P, R) 水平对。"""
        fam = self.best["family"]; par = self.best["par"]
        u = rng.random(n)
        v = np.array([CP.hinv(fam, rng.random(), u[i], par) for i in range(n)])
        return self.mP.ppf(u), self.mR.ppf(v)

    def summary(self) -> dict:
        return dict(best=dict(family=self.best["family"],
                              par=np.asarray(self.best["par"]).tolist(),
                              loglik=self.best["loglik"], aic=self.best["aic"],
                              ecdist=self.best["ecdist"],
                              tail=list(self.best["tail"]),
                              tau_sim=self.best["tau_sim"]),
                    candidates=[dict(family=c["family"],
                                     par=np.asarray(c["par"]).tolist(),
                                     loglik=c["loglik"], aic=c["aic"],
                                     ecdist=c["ecdist"],
                                     tail=list(c["tail"]),
                                     tau_sim=c["tau_sim"]) for c in self.cands])


# --------------------------------------------------------------------------
# 场景生成
# --------------------------------------------------------------------------
def generate(panel, train_dates, K=60, n_draw=600, seed=7, k_nn=10, reduce="strat"):
    """由训练窗数据拟合 Copula 并生成 K 条联合场景。"""
    lv = daily_levels(panel, train_dates)
    cop = LevelCopula()
    cop.fit(lv["P"], lv["R"])
    ps, rs, R = _shapes(lv["price"], lv["resid"])
    # 水平标准化（用于近邻搜索）
    sdP = lv["P"].std(ddof=1); sdR = lv["R"].std(ddof=1)
    zP = (lv["P"] - lv["P"].mean()) / sdP
    zR = (lv["R"] - lv["R"].mean()) / sdR
    rng = np.random.default_rng(seed)
    Ps, Rs = cop.sample_levels(n_draw, rng)
    zPs = (Ps - lv["P"].mean()) / sdP
    zRs = (Rs - lv["R"].mean()) / sdR
    price_s = np.zeros((n_draw, C.N_SLOT))
    resid_s = np.zeros((n_draw, C.N_SLOT))
    for i in range(n_draw):
        dist = (zPs[i] - zP) ** 2 + (zRs[i] - zR) ** 2
        near = np.argsort(dist)[:k_nn]
        j = int(rng.choice(near))
        price_s[i] = ps[j] + Ps[i]                      # 形状 + 抽到的日水平
        resid_s[i] = rs[j] * Rs[i]                      # 归一形状 × 抽到的日总残差
    if reduce == "none":
        cen_p, cen_r, w = price_s, resid_s, np.full(n_draw, 1.0 / n_draw)
    elif reduce == "strat":
        cen_r, w = LP.reduce_scenarios_stratified(resid_s, K=K)
        # 代表行的电价随之取出（stratified 返回的是代表行本身）
        cen_p = _match_rows(resid_s, cen_r, price_s)
    elif reduce == "kmeans":
        cen_r, w = LP.reduce_scenarios(resid_s, K=K, seed=seed)
        cen_p = _match_rows(resid_s, cen_r, price_s)
    else:
        raise ValueError(reduce)
    return dict(price=cen_p, resid=cen_r, w=np.asarray(w, float) / np.sum(w),
                net=None, src=None, kind="fixed", copula=cop)


def _match_rows(src, cen, val):
    """把代表场景（cen 行）映射回原始行下标，取对应的价格行。"""
    out = np.zeros((cen.shape[0], val.shape[1]))
    for k in range(cen.shape[0]):
        d = ((src - cen[k]) ** 2).sum(1)
        out[k] = val[int(np.argmin(d))]
    return out


# --------------------------------------------------------------------------
# 保真度度量（水平 + 形状 + 相依）
# --------------------------------------------------------------------------
def wquant(x, w, q):
    """加权分位数（q 为 0-100 的百分位数组）。"""
    x = np.asarray(x, float); w = np.asarray(w, float)
    o = np.argsort(x); x, w = x[o], w[o]
    cw = (np.cumsum(w) - 0.5 * w) / np.sum(w)
    return np.interp(np.asarray(q, float) / 100.0, cw, x)


def generate_relative(panel, train_dates, K=60):
    """相对残差情景集：r_t / (当日光伏预报电量)，供"按当日规模缩放"的条件情景使用。"""
    lv = daily_levels(panel, train_dates)
    fc = np.vstack([panel.pv_forecast(d, 0) for d in train_dates])
    pvfc = fc.sum(1) * C.DT
    rel = lv["resid"] / pvfc[:, None]
    cen, w = LP.reduce_scenarios_stratified(rel, K=K)
    return dict(rel=cen, w=w,
                rel_mu=float((cen * w[:, None]).sum()),
                rel_sd=float(np.sqrt((w[:, None] * (cen - (cen * w[:, None]).sum(0)) ** 2).sum())))


def fidelity(scen, panel, dates):
    """与真实分布的对比：水平边际分位差、Kendall tau、联合尾共现率。"""
    from scipy import stats
    lv = daily_levels(panel, dates)
    P, R = lv["P"], lv["R"]
    Ps = scen["price"].mean(1)
    Rs = scen["resid"].sum(1)
    w = scen["w"] / scen["w"].sum()
    qs = [1, 5, 25, 50, 75, 95, 99]
    out = {}
    for tag, a, b in (("P", P, Ps), ("R", R, Rs)):
        qa = np.percentile(a, qs)
        qb = wquant(b, w, qs)
        out[f"{tag}_q_true"] = qa.tolist()
        out[f"{tag}_q_scen"] = qb.tolist()
        out[f"{tag}_maxq_gap"] = float(np.max(np.abs(qb - qa) / np.maximum(np.abs(qa), 1e-9)))
        out[f"{tag}_absq_gap"] = float(np.max(np.abs(qb - qa)))
    out["tau_true_PR"] = float(stats.kendalltau(P, R).statistic)
    out["tau_scen_PR"] = float(_wtau(Ps, Rs, w))
    # 联合尾共现（P 高 & R 高 = 高价叠加光伏高估；P 低 & R 低 = 低价叠加光伏低估）
    for tag, fn in (("hi_hi", lambda a, b, q: (a > np.quantile(a, q)) & (b > np.quantile(b, q))),
                    ("lo_lo", lambda a, b, q: (a < np.quantile(a, q)) & (b < np.quantile(b, q)))):
        q = 0.75 if tag == "hi_hi" else 0.25
        out[f"tail_true_{tag}"] = float(np.mean(fn(P, R, q)))
        out[f"tail_scen_{tag}"] = float(_wmean_abs(fn(Ps, Rs, q).astype(float), w))
    return out


def _wtau(x, y, w):
    """加权 Kendall tau（成对符号法，n<=200 时可接受）。"""
    x = np.asarray(x, float); y = np.asarray(y, float); w = np.asarray(w, float)
    n = len(x)
    if n > 400:
        idx = np.argsort(-w)[:400]
        x, y, w = x[idx], y[idx], w[idx]
        n = len(x)
    num = den = 0.0
    for i in range(n):
        s = np.sign(x[i] - x) * np.sign(y[i] - y)
        c = w[i] * w
        num += 0.5 * np.sum(c * s)
        den += 0.5 * np.sum(c)
    return float(num / max(den, 1e-12))


def _wmean_abs(flag, w):
    return float(np.sum(flag * w) / np.sum(w))
