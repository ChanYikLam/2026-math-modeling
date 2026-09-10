# -*- coding: utf-8 -*-
"""
单日两阶段 LP 求解引擎（问题 2 / 问题 3 / 问题 4 共用）
=====================================================
变量（全部为 kWh）：
    E_t        计划购电量（第一阶段承诺量）
    c_t, d_t   充电量 / 放电量
    S_t        时段末储电量
    g_{w,t}    情景 w 下的紧急购电量（第二阶段追索）

模型：
    min  sum_t p_t E_t + 5 * sum_t p_t * sum_w W_w g_{w,t}
    s.t. E_t - c_t + d_t                >= ND^fcst_t                  (计划满足预测负载)
         g_{w,t} + E_t - c_t + d_t      >= ND^act_{w,t}               (实际缺口 -> 紧急购电)
         S_t = S_{t-1} + eta_c c_t - d_t/eta_d
         S_min <= S_t <= S_max, 0 <= c_t,d_t <= E_MAX, E_t>=0, g>=0
         S_144 >= S_0（A6 终端不亏空）或 = S_0（严格日周期）

ND = (L - PV) * DT 为"净需求"电量。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack

import config as C


def solve_day(price, nd_fcst, nd_scen, weights=None, s_init=C.S_INIT,
              term_mode="ge", term_value=None, allow_overbuy=True):
    """求解单日两阶段 LP。

    参数
    ----
    price    : (n,) 电价 元/kWh
    nd_fcst  : (n,) 预测口径净需求 (L_fcst - PV_fcst)*DT，单位 kWh
    nd_scen  : (K,n) 各情景实际净需求 (L_act - PV_act)*DT，单位 kWh
    weights  : (K,) 情景概率，默认等权
    s_init   : 日初储电量
    term_mode: 'ge' -> S_n >= s_init；'eq' -> S_n = s_init；'free' -> S_n >= S_min
    """
    n = C.N_SLOT
    nd_scen = np.atleast_2d(nd_scen)
    K = nd_scen.shape[0]
    if weights is None:
        weights = np.full(K, 1.0 / K)
    weights = np.asarray(weights, float)
    weights = weights / weights.sum()

    iE, iC, iD, iS, iG = 0, n, 2 * n, 3 * n, 4 * n
    nv = 4 * n + K * n

    c_obj = np.zeros(nv)
    c_obj[iE:iE + n] = price
    for w in range(K):
        c_obj[iG + w * n: iG + (w + 1) * n] = C.EMERGENCY_MULT * price * weights[w]

    rows, cols, vals, rhs = [], [], [], []

    def add(row, col, val):
        rows.append(row); cols.append(col); vals.append(val)

    r = 0
    # (1) 计划可行性
    for t in range(n):
        add(r, iE + t, -1.0); add(r, iC + t, 1.0); add(r, iD + t, -1.0)
        rhs.append(-nd_fcst[t]); r += 1
    # (2) 紧急购电（>= 形式）
    for w in range(K):
        for t in range(n):
            add(r, iE + t, -1.0); add(r, iC + t, 1.0); add(r, iD + t, -1.0)
            add(r, iG + w * n + t, -1.0)
            rhs.append(-nd_scen[w, t]); r += 1
    A_ub = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
    b_ub = np.array(rhs)

    # (3) SOC 递推等式
    rows2, cols2, vals2, rhs2 = [], [], [], []
    for t in range(n):
        rr = t
        vals2.append(1.0); cols2.append(iS + t); rows2.append(rr)
        if t > 0:
            vals2.append(-1.0); cols2.append(iS + t - 1); rows2.append(rr)
        vals2.append(-C.ETA_C); cols2.append(iC + t); rows2.append(rr)
        vals2.append(1.0 / C.ETA_D); cols2.append(iD + t); rows2.append(rr)
        rhs2.append(0.0 if t > 0 else s_init)
    A_eq = coo_matrix((vals2, (rows2, cols2)), shape=(n, nv)).tocsr()
    b_eq = np.array(rhs2)

    bounds = [(0.0, None)] * n + [(0.0, C.E_MAX)] * n + [(0.0, C.E_MAX)] * n + \
             [(C.S_MIN, C.S_MAX)] * n + [(0.0, None)] * (K * n)
    if term_mode == "eq":
        v = s_init if term_value is None else term_value
        bounds[iS + n - 1] = (v, v)
    elif term_mode == "ge":
        v = s_init if term_value is None else term_value
        bounds[iS + n - 1] = (max(v, C.S_MIN), C.S_MAX)

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError("LP 不可行：" + res.message)
    x = res.x
    out = dict(E=x[iE:iE + n].copy(), c=x[iC:iC + n].copy(),
               d=x[iD:iD + n].copy(), S=x[iS:iS + n].copy(),
               g=x[iG:iG + K * n].reshape(K, n).copy(),
               obj=res.fun, s_init=s_init, K=K, weights=weights,
               nd_fcst=nd_fcst, nd_scen=nd_scen, price=price,
               dual_eq=res.eqlin.marginals.copy(),
               dual_plan=res.ineqlin.marginals[:n].copy(),
               status=res.status)
    return out


def realized_slot(sol, nd_act):
    """给定实际净需求，按"计划照常执行 + 缺口紧急购电"结算，返回逐槽紧急购电量与费用。"""
    n = C.N_SLOT
    g = np.maximum(nd_act + sol["c"] - sol["d"] - sol["E"], 0.0)
    plan_cost = float(np.sum(sol["price"] * sol["E"]))
    emg_cost = float(C.EMERGENCY_MULT * np.sum(sol["price"] * g))
    return g, plan_cost, emg_cost


def solve_epoch(price, nd_fcst, nd_scen, weights, s_init, s_from=0,
                plan=None, term_floor=None, tol_tail=None):
    """滚动时域中"某一预报时刻"的子问题 LP（只优化槽位 [s_from, n)）。

    plan 不为 None 时启用 Q3 的调整/违约定价口径：
        cost_t = p*min(E^plan,E) + 0.5p (E^plan-E)^+ + 1.5p (E-E^plan)^+
    线性化为  p*E^plan - 0.5p u + 1.5p v,  E - E^plan = v - u,  u,v >= 0。
    """
    n = C.N_SLOT
    nd_scen = np.atleast_2d(nd_scen)
    K = nd_scen.shape[0]
    if weights is None:
        weights = np.full(K, 1.0 / K)
    weights = np.asarray(weights, float); weights = weights / weights.sum()
    m = n - s_from                                   # 本时段数
    use_plan = plan is not None and s_from > 0

    iE, iC, iD, iS, iG = 0, m, 2 * m, 3 * m, 4 * m
    iU = iG + K * m
    nv = 4 * m + K * m + (2 * m if use_plan else 0)

    c_obj = np.zeros(nv)
    if use_plan:
        c_obj[iU:iU + m] = -C.BREACH_MULT * price[s_from:]          # -0.5p u
        c_obj[iU + m:iU + 2 * m] = C.EXCESS_MULT * price[s_from:]   # +1.5p v
    else:
        c_obj[iE:iE + m] = price[s_from:]
    for w in range(K):
        c_obj[iG + w * m:iG + (w + 1) * m] = C.EMERGENCY_MULT * price[s_from:] * weights[w]

    rows, cols, vals, rhs = [], [], [], []
    r = 0
    for j in range(m):
        add = (r, iE + j, -1.0), (r, iC + j, 1.0), (r, iD + j, -1.0)
        for a, b, c_ in add:
            rows.append(a); cols.append(b); vals.append(c_)
        rhs.append(-nd_fcst[s_from + j]); r += 1
    for w in range(K):
        for j in range(m):
            for a, b, c_ in ((r, iE + j, -1.0), (r, iC + j, 1.0),
                             (r, iD + j, -1.0), (r, iG + w * m + j, -1.0)):
                rows.append(a); cols.append(b); vals.append(c_)
            rhs.append(-nd_scen[w, s_from + j]); r += 1
    if use_plan:
        for j in range(m):
            for a, b, c_ in ((r, iE + j, 1.0), (r, iU + m + j, -1.0),
                             (r, iU + j, 1.0)):
                rows.append(a); cols.append(b); vals.append(c_)
            rhs.append(plan[s_from + j]); r += 1
    A_ub = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
    b_ub = np.array(rhs)

    rows2, cols2, vals2, rhs2 = [], [], [], []
    for j in range(m):
        t = s_from + j
        for b, c_ in ((iS + j, 1.0), (iC + j, -C.ETA_C), (iD + j, 1.0 / C.ETA_D)):
            rows2.append(j); cols2.append(b); vals2.append(c_)
        if j > 0:
            rows2.append(j); cols2.append(iS + j - 1); vals2.append(-1.0)
        rhs2.append(0.0 if j > 0 else s_init)
    A_eq = coo_matrix((vals2, (rows2, cols2)), shape=(m, nv)).tocsr()
    b_eq = np.array(rhs2)

    bounds = [(0.0, None)] * m + [(0.0, C.E_MAX)] * m + [(0.0, C.E_MAX)] * m + \
             [(C.S_MIN, C.S_MAX)] * m + [(0.0, None)] * (K * m) + \
             ([(0.0, None)] * (2 * m) if use_plan else [])
    if term_floor is not None:
        bounds[iS + m - 1] = (max(term_floor, C.S_MIN), C.S_MAX)

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError("epoch LP 不可行：" + res.message)
    x = res.x
    out = dict(E=x[iE:iE + m].copy(), c=x[iC:iC + m].copy(),
               d=x[iD:iD + m].copy(), S=x[iS:iS + m].copy(),
               g=x[iG:iG + K * m].reshape(K, m).copy(), obj=res.fun,
               s_from=s_from, K=K)
    if use_plan:
        out["u"] = x[iU:iU + m].copy(); out["v"] = x[iU + m:iU + 2 * m].copy()
    return out


def check_solution(sol, nd_fcst, nd_act=None, tol=1e-7):
    """独立可行性自检（不依赖求解器返回值）。"""
    n = C.N_SLOT
    E, c, d, S = sol["E"], sol["c"], sol["d"], sol["S"]
    rep = {}
    rep["R1_plan_violation"] = float(np.max(nd_fcst + c - d - E))        # <= tol
    rep["R2_power_violation"] = float(max(np.max(c), np.max(d)) - C.E_MAX)
    rep["R3_soc_bounds"] = float(max(C.S_MIN - S.min(), S.max() - C.S_MAX))
    prev = np.concatenate([[sol["s_init"]], S[:-1]])
    rep["R4_soc_recursion"] = float(np.max(np.abs(S - (prev + C.ETA_C * c - d / C.ETA_D))))
    rep["R5_simultaneous"] = int(np.sum((c > 1e-6) & (d > 1e-6)))
    if nd_act is not None:
        g = np.maximum(nd_act + c - d - E, 0.0)
        rep["R6_emergency_consistency"] = float(np.max(
            np.abs(g - np.maximum(nd_act + c - d - E, 0.0))))
        rep["R7_min_supply_surplus"] = float(np.min(E + d - c - nd_act))
    return rep


def reduce_scenarios_stratified(resid, K=60):
    """按日总残差分层，层内取 medoid 为代表，权重=层样本占比。

    相比 K-means，分层抽样**显式保留残差分布的尾部**（每个分位区间都有代表），
    避免均值化把 5 倍紧急购电所需的安全边际抹平。
    """
    s = resid.sum(axis=1)
    order = np.argsort(s)
    groups = np.array_split(order, K)
    cen, w = [], []
    for g in groups:
        if len(g) == 0:
            continue
        sub = resid[g]
        if len(g) == 1:
            cen.append(sub[0])
        else:
            dist = np.sqrt(((sub[:, None, :] - sub[None, :, :]) ** 2).sum(-1))
            cen.append(sub[int(np.argmin(dist.sum(1)))])
        w.append(len(g) / len(s))
    return np.array(cen), np.array(w)


def reduce_scenarios(resid, K=30, seed=0):
    """对残差样本做 K-means 场景削减，返回（代表场景, 权重）。"""
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=K, n_init=4, random_state=seed).fit(resid)
    lab = km.labels_
    cen = km.cluster_centers_
    w = np.array([np.sum(lab == k) for k in range(K)], float) / len(lab)
    keep = w > 0
    return cen[keep], w[keep]
