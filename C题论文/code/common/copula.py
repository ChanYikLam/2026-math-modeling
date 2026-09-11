# -*- coding: utf-8 -*-
"""
二元 Copula 工具库 + 藤 Copula（pair-Copula）联合建模
====================================================
对应参考论文：
  · 宁楠《基于动态 C 藤 pair-Copula 的电力系统动态经济调度》—— C 藤结构、逐层二元 Copula、
    以与经验 Copula 的距离选族；
  · 崔丽敏等《基于核密度估计和 Copula 函数的风-光-荷联合场景生成》—— KDE 边缘 + Copula 相依
    + 蒙特卡洛抽样。

本文件只依赖 numpy/scipy，自行实现五个常用二元 Copula 族（Gaussian / t / Clayton /
Gumbel / Frank）的密度、h 函数（条件分布）与 h 逆函数，用于：
  1) 用极大似然 + AIC 在候选族中选优（并同时报告与经验 Copula 的欧氏距离）；
  2) 计算上/下尾相依系数，量化"高峰又贵又缺"的尾部聚集；
  3) 通过 C 藤逐层采样生成联合场景。

约定：所有函数输入 u, v ∈ (0,1)（伪观测或分布函数值）。
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # -> code/
import _pathsetup  # noqa: E402,F401  子目录引导：把 common/ 与各问目录加入 sys.path

import numpy as np
from scipy import stats, special
from scipy.optimize import brentq, minimize

EPS = 1e-10
FAMILIES = ("gaussian", "t", "clayton", "gumbel", "frank")
# 多元正态/t 的数值积分用固定随机源，保证经验 Copula 距离可复现
_CDF_RNG = np.random.default_rng(20260910)


# --------------------------------------------------------------------------
# 二元 Copula 对数密度
# --------------------------------------------------------------------------
def logpdf(family, u, v, par):
    u = np.clip(np.asarray(u, float), EPS, 1 - EPS)
    v = np.clip(np.asarray(v, float), EPS, 1 - EPS)
    if family == "gaussian":
        rho = float(np.clip(par[0], -0.999, 0.999))
        x, y = stats.norm.ppf(u), stats.norm.ppf(v)
        s = 1.0 - rho ** 2
        return -0.5 * np.log(s) - (rho ** 2 * (x ** 2 + y ** 2) - 2 * rho * x * y) / (2 * s)
    if family == "t":
        rho = float(np.clip(par[0], -0.999, 0.999))
        nu = float(np.clip(par[1], 2.05, 80.0))
        x, y = stats.t.ppf(u, nu), stats.t.ppf(v, nu)
        s = 1.0 - rho ** 2
        ll = (special.gammaln((nu + 2) / 2) + special.gammaln(nu / 2)
              - 2 * special.gammaln((nu + 1) / 2) - 0.5 * np.log(s))
        num = -(nu + 2) / 2 * np.log1p((x ** 2 + y ** 2 - 2 * rho * x * y) / (nu * s))
        den = -(nu + 1) / 2 * (np.log1p(x ** 2 / nu) + np.log1p(y ** 2 / nu))
        return ll + num - den
    if family == "clayton":
        th = float(np.clip(par[0], 1e-3, 30.0))
        return (np.log1p(th) - (1 + th) * (np.log(u) + np.log(v))
                - (2 + 1 / th) * np.log(np.power(u, -th) + np.power(v, -th) - 1))
    if family == "gumbel":
        th = float(np.clip(par[0], 1.0 + 1e-4, 20.0))
        lu, lv = -np.log(u), -np.log(v)
        A = np.power(lu ** th + lv ** th, 1.0 / th)
        return (-A + (th - 1) * (np.log(lu) + np.log(lv)) - np.log(u) - np.log(v)
                + (1.0 / th - 2) * np.log(lu ** th + lv ** th) + np.log(A + th - 1))
    if family == "frank":
        th = float(par[0])
        if abs(th) < 1e-6:
            return np.zeros_like(u)
        e = np.exp(-th)
        num = np.log(abs(th)) + np.log(abs(1 - e)) - th * (u + v)
        den = 2 * np.log(np.abs((1 - e) - (1 - np.exp(-th * u)) * (1 - np.exp(-th * v))))
        return num - den
    raise ValueError(family)


def loglik(family, u, v, par) -> float:
    return float(np.sum(logpdf(family, u, v, par)))


# --------------------------------------------------------------------------
# 参数域与初值（用 Kendall tau 反演给初值，按族给出界）
# --------------------------------------------------------------------------
def _tau(u, v) -> float:
    return float(stats.kendalltau(u, v).statistic)


def init_and_bounds(family, u, v):
    tau = _tau(u, v)
    if family == "gaussian":
        return [np.sin(np.pi * tau / 2)], [(-0.995, 0.995)]
    if family == "t":
        return [np.sin(np.pi * tau / 2), 6.0], [(-0.995, 0.995), (2.1, 60.0)]
    if family == "clayton":
        th = max(2 * tau / (1 - tau), 0.05) if tau > 0 else 0.05
        return [th], [(1e-3, 30.0)]
    if family == "gumbel":
        th = 1.0 / (1 - tau) if tau > 0 else 1.05
        return [min(max(th, 1.001), 19.0)], [(1.001, 20.0)]
    if family == "frank":
        return [4.0 * np.sign(tau) * max(abs(tau), 0.05)], [(-40.0, 40.0)]
    raise ValueError(family)


def fit(family, u, v):
    """极大似然拟合单个二元 Copula，返回 dict(par, loglik, aic)。"""
    x0, bnds = init_and_bounds(family, u, v)

    def nll(p):
        ll = loglik(family, u, v, p)
        return -ll if np.isfinite(ll) else 1e12
    best = None
    for scale in (1.0, 0.5, 1.5):
        try:
            r = minimize(nll, np.array(x0) * scale, method="L-BFGS-B", bounds=bnds,
                         options=dict(maxiter=400, ftol=1e-10))
        except Exception:
            continue
        if np.isfinite(r.fun) and (best is None or r.fun < best.fun):
            best = r
    if best is None:
        raise RuntimeError(f"{family} 拟合失败")
    par = np.asarray(best.x, float)
    ll = -float(best.fun)
    k = len(par)
    return dict(family=family, par=par, loglik=ll, aic=2 * k - 2 * ll, k=k)


# --------------------------------------------------------------------------
# h 函数（条件分布）与 h 逆
# --------------------------------------------------------------------------
def hfunc(family, u, v, par):
    """h(u|v) = dC(u,v)/dv，返回与 u 同形的数组。"""
    u = np.clip(np.asarray(u, float), EPS, 1 - EPS)
    v = np.clip(np.asarray(v, float), EPS, 1 - EPS)
    if family == "gaussian":
        rho = float(np.clip(par[0], -0.999, 0.999))
        x, y = stats.norm.ppf(u), stats.norm.ppf(v)
        return stats.norm.cdf((x - rho * y) / np.sqrt(1 - rho ** 2))
    if family == "t":
        rho = float(np.clip(par[0], -0.999, 0.999))
        nu = float(np.clip(par[1], 2.05, 80.0))
        x, y = stats.t.ppf(u, nu), stats.t.ppf(v, nu)
        arg = (x - rho * y) * np.sqrt((nu + 1) / ((nu + y ** 2) * (1 - rho ** 2)))
        return stats.t.cdf(arg, nu + 1)
    if family == "clayton":
        th = float(np.clip(par[0], 1e-3, 30.0))
        return np.power(v, -th - 1) * np.power(np.power(u, -th) + np.power(v, -th) - 1,
                                               -1 / th - 1)
    if family == "gumbel":
        th = float(np.clip(par[0], 1.0 + 1e-4, 20.0))
        lu, lv = -np.log(u), -np.log(v)
        A = np.power(lu ** th + lv ** th, 1.0 / th)
        return np.exp(-A) * np.power(lv, th - 1) * np.power(lu ** th + lv ** th,
                                                            1.0 / th - 1) / v
    if family == "frank":
        th = float(par[0])
        if abs(th) < 1e-6:
            return u.copy()
        e = np.exp(-th)
        num = (np.exp(-th * u) - 1) * np.exp(-th * v)
        den = (e - 1) + (np.exp(-th * u) - 1) * (np.exp(-th * v) - 1)
        return num / den
    raise ValueError(family)


def hinv(family, target, v, par):
    """求 u 使 h(u|v) = target（标量 target/v）。"""
    def f(u):
        return float(hfunc(family, u, v, par)) - target
    lo, hi = EPS, 1 - EPS
    flo, fhi = f(lo), f(hi)
    if flo > 0:
        return lo
    if fhi < 0:
        return hi
    return brentq(f, lo, hi, xtol=1e-12, rtol=1e-12, maxiter=200)


# --------------------------------------------------------------------------
# 经验 Copula 距离与尾相依系数
# --------------------------------------------------------------------------
def empirical_copula_distance(family, u, v, par, ngrid=40) -> float:
    """与经验 Copula 的 L2 距离（在 ngrid x ngrid 网格上）。

    注意：Gaussian / t 的 Copula 分布函数由 scipy 的随机化数值积分给出，
    为**可复现**起见在此固定随机源（rng），否则同一数据两次运行会得到末位不同的距离。
    """
    g = np.linspace(0.02, 0.98, ngrid)
    U, V = np.meshgrid(g, g, indexing="ij")
    emp = np.array([[np.mean((u <= a) & (v <= b)) for b in g] for a in g])
    th = copula_cdf(family, U, V, par)
    return float(np.sqrt(np.mean((emp - th) ** 2)))


def _t_cdf(x, rho, nu):
    """二元 t 分布函数：固定随机源以保证可复现（scipy 的数值积分是随机化的）。"""
    kw = dict(loc=[0, 0], shape=[[1, rho], [rho, 1]], df=nu)
    try:
        return stats.multivariate_t.cdf(x, rng=_CDF_RNG, **kw)
    except TypeError:
        state = np.random.get_state()
        np.random.seed(20260910)
        try:
            return stats.multivariate_t.cdf(x, **kw)
        finally:
            np.random.set_state(state)


def copula_cdf(family, u, v, par):
    u = np.clip(np.asarray(u, float), EPS, 1 - EPS)
    v = np.clip(np.asarray(v, float), EPS, 1 - EPS)
    if family == "gaussian":
        rho = float(np.clip(par[0], -0.999, 0.999))
        x, y = stats.norm.ppf(u), stats.norm.ppf(v)
        return stats.multivariate_normal.cdf(np.stack([x, y], -1), mean=[0, 0],
                                             cov=[[1, rho], [rho, 1]],
                                             rng=_CDF_RNG)
    if family == "t":
        rho = float(np.clip(par[0], -0.999, 0.999))
        nu = float(np.clip(par[1], 2.05, 80.0))
        x, y = stats.t.ppf(u, nu), stats.t.ppf(v, nu)
        return _t_cdf(np.stack([x, y], -1), rho, nu)
    if family == "clayton":
        th = float(np.clip(par[0], 1e-3, 30.0))
        return np.power(np.power(u, -th) + np.power(v, -th) - 1, -1 / th)
    if family == "gumbel":
        th = float(np.clip(par[0], 1.0 + 1e-4, 20.0))
        return np.exp(-np.power((-np.log(u)) ** th + (-np.log(v)) ** th, 1 / th))
    if family == "frank":
        th = float(par[0])
        if abs(th) < 1e-6:
            return u * v
        e = np.exp(-th)
        return -1 / th * np.log1p((np.exp(-th * u) - 1) * (np.exp(-th * v) - 1) / (e - 1))
    raise ValueError(family)


def tail_dependence(family, par):
    """返回 (上尾, 下尾) 相依系数 λ_U, λ_L。"""
    if family == "gaussian":
        rho = float(par[0])
        return (0.0, 0.0) if abs(rho) < 1 else (1.0, 1.0)
    if family == "t":
        rho, nu = float(par[0]), float(par[1])
        lam = 2 * stats.t.cdf(-np.sqrt((nu + 1) * (1 - rho) / (1 + rho)), nu + 1)
        return float(lam), float(lam)
    if family == "clayton":
        return 0.0, float(2 ** (-1 / float(par[0])))
    if family == "gumbel":
        return float(2 - 2 ** (1 / float(par[0]))), 0.0
    if family == "frank":
        return 0.0, 0.0
    raise ValueError(family)


# --------------------------------------------------------------------------
# 边缘分布：核密度估计（KDE）
# --------------------------------------------------------------------------
class KdeMarginal:
    """一维 KDE 边缘分布，提供 cdf / ppf / pdf。"""

    def __init__(self, x, bw=None, n_grid=2001):
        x = np.asarray(x, float)
        self.x = x
        self.kde = stats.gaussian_kde(x, bw_method=bw)
        sd = float(x.std(ddof=1)) if len(x) > 1 else 1.0
        lo = float(x.min()) - 3.0 * sd
        hi = float(x.max()) + 3.0 * sd
        g = np.linspace(lo, hi, n_grid)
        d = self.kde(g)
        c = np.concatenate([[0.0], np.cumsum((d[1:] + d[:-1]) / 2 * np.diff(g))])
        c = c / c[-1]
        self._g, self._c, self._d = g, c, d

    def cdf(self, x):
        return np.interp(x, self._g, self._c, left=0.0, right=1.0)

    def ppf(self, u):
        return np.interp(np.clip(u, 0.0, 1.0), self._c, self._g)

    def pdf(self, x):
        return self.kde(np.atleast_1d(x))

    def sample(self, n, rng):
        return self.kde.resample(n, seed=rng)[0]


def pseudo_obs(x):
    """伪观测：(rank - 0.5)/n。"""
    x = np.asarray(x, float)
    r = stats.rankdata(x)
    return (r - 0.5) / len(x)


# --------------------------------------------------------------------------
# C 藤（pair-Copula）联合建模：3 变量，根节点为第 0 个变量
# --------------------------------------------------------------------------
class CVine3:
    """三变量 C 藤：

        c(u1,u2,u3) = c12(u1,u2) · c13(u1,u3) · c23|1(h(u2|u1), h(u3|u1))

    根节点为 u1（本题取电价）。逐层二元 Copula 族由 AIC 在 5 个候选族中选出。
    """

    def __init__(self, names=("price", "load", "pv")):
        self.names = names
        self.marg = [None, None, None]
        self.tree = {}

    def fit(self, X, verbose=False):
        """X: (n,3) 原始数据；返回选族结果表。"""
        X = np.asarray(X, float)
        n = len(X)
        for j in range(3):
            self.marg[j] = KdeMarginal(X[:, j])
        U = np.column_stack([pseudo_obs(X[:, j]) for j in range(3)])
        self.U = U
        rows = []
        # 第 1 层：c12, c13
        for (i, j) in ((0, 1), (0, 2)):
            rows.append(self._fit_pair(f"T1_{self.names[i]}_{self.names[j]}", U[:, i], U[:, j]))
        # 第 2 层：c23|1
        e2 = hfunc(self.tree["T1_price_load"]["family"], U[:, 1], U[:, 0],
                   self.tree["T1_price_load"]["par"])
        e3 = hfunc(self.tree["T1_price_pv"]["family"], U[:, 2], U[:, 0],
                   self.tree["T1_price_pv"]["par"])
        rows.append(self._fit_pair(f"T2_{self.names[1]}_{self.names[2]}|{self.names[0]}", e2, e3))
        if verbose:
            for r in rows:
                print(f"  {r['name']:26s} 最优族={r['best']:9s} 参数={np.round(r['par'],4)} "
                      f"AIC={r['aic']:.2f} 经验距离={r['ecdist']:.4f}")
        return rows

    def _fit_pair(self, name, u, v):
        cands = []
        for fam in FAMILIES:
            try:
                f = fit(fam, u, v)
            except Exception:
                continue
            f["ecdist"] = empirical_copula_distance(fam, u, v, f["par"])
            f["tau_emp"] = _tau(u, v)
            f["tau_fit"] = None
            cands.append(f)
        cands.sort(key=lambda d: d["aic"])
        best = cands[0]
        rec = dict(name=name, best=best["family"], par=best["par"].tolist(),
                   loglik=best["loglik"], aic=best["aic"],
                   ecdist=best["ecdist"], tau_emp=best["tau_emp"],
                   candidates=[dict(family=c["family"], par=c["par"].tolist(),
                                    loglik=c["loglik"], aic=c["aic"],
                                    ecdist=c["ecdist"]) for c in cands])
        self.tree[name] = dict(family=best["family"], par=best["par"])
        # 同时给出该对的 tau 与尾相依
        rec["tail"] = tail_dependence(best["family"], best["par"])
        return rec

    def sample_copula(self, n, rng):
        """按 C 藤逐层采样，返回 (n,3) 的 (u1,u2,u3)。"""
        t12 = self.tree["T1_price_load"]; t13 = self.tree["T1_price_pv"]
        t23 = self.tree["T2_load_pv|price"]
        w = rng.random((n, 3))
        u1 = w[:, 0]
        u2 = np.array([hinv(t12["family"], w[i, 1], u1[i], t12["par"]) for i in range(n)])
        e2 = hfunc(t12["family"], u2, u1, t12["par"])
        e3 = np.array([hinv(t23["family"], w[i, 2], e2[i], t23["par"]) for i in range(n)])
        u3 = np.array([hinv(t13["family"], e3[i], u1[i], t13["par"]) for i in range(n)])
        return np.column_stack([u1, u2, u3])
