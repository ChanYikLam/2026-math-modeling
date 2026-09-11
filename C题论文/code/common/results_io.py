# -*- coding: utf-8 -*-
"""结果文件写出器（严格按附件 5 模板的列序、列名、日期范围）。"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # -> code/
import _pathsetup  # noqa: E402,F401  子目录引导：把 common/ 与各问目录加入 sys.path

import os

import numpy as np
import pandas as pd

import config as C


def _labels(fname: str, sheet: str):
    t = C.read_template(sheet, fname, nrows=1)
    return [str(v) for v in t.iloc[0].tolist()]


def plan_sheet_frame(dates, E, price, price_mat=None) -> pd.DataFrame:
    """横表：日期 + 144 槽 + 全天购电量 + 全天购电费。"""
    labels = _labels("result2.xlsx", "计划购电量")
    slot_labels = labels[1:145]
    assert len(slot_labels) == C.N_SLOT, len(slot_labels)
    cols = ["日期\\时间"] + slot_labels + ["全天购电量", "全天购电费"]
    rows = []
    for i, d in enumerate(dates):
        p = price if price_mat is None else price_mat[i]
        rows.append([d.strftime("%Y-%m-%d")] + list(np.round(E[i], 4)) +
                    [round(float(E[i].sum()), 4), round(float(np.sum(p * E[i])), 2)])
    return pd.DataFrame(rows, columns=cols)


def soc_sheet_frame(dates, c, d, s0, s1) -> pd.DataFrame:
    """充放电量：每天 6 行（4 h 块），0:00 储电量填在 0:00-4:00 行、24:00 填在 4:00-8:00 行。"""
    rows = []
    for i, day in enumerate(dates):
        for b, ((a, bnd), lab) in enumerate(zip(C.BLOCKS, C.BLOCK_LABELS)):
            rec = [(day.strftime("%Y-%m-%d") if b == 0 else ""), lab,
                   round(float(c[i, a:bnd].sum()), 4), round(float(d[i, a:bnd].sum()), 4),
                   "", ""]
            if b == 0:
                rec[4] = "0:00"; rec[5] = round(float(s0[i]), 4)
            if b == 1:
                rec[4] = "24:00"; rec[5] = round(float(s1[i]), 4)
            rows.append(rec)
    return pd.DataFrame(rows, columns=["日期", "时间段", "充电量", "放电量", "时刻", "储电量"])


def emergency_frame(dates, g, tol=1e-6) -> pd.DataFrame:
    """紧急购电量：按连续时段合并，同一日期可多行。"""
    rows = []
    for i, day in enumerate(dates):
        gi = g[i]
        idx = np.where(gi > tol)[0]
        if len(idx) == 0:
            rows.append([day.strftime("%Y-%m-%d"), "无", 0.0])
            continue
        # 合并连续槽
        groups, start = [], idx[0]
        for a, b in zip(idx[:-1], idx[1:]):
            if b != a + 1:
                groups.append((start, a)); start = b
        groups.append((start, idx[-1]))
        first = True
        for a, b in groups:
            lab = f"{_hm(a)}-{_hm(b + 1)}"
            rows.append([day.strftime("%Y-%m-%d") if first else "", lab,
                         round(float(gi[a:b + 1].sum()), 4)])
            first = False
    return pd.DataFrame(rows, columns=["日期", "购电时间段", "购电量"])


def _hm(slot_end: int) -> str:
    """槽位末端的时刻标签，例如槽 5 结束 -> 1:00。"""
    m = slot_end * 10
    if m >= 1440:
        m -= 1440
        return f"{m // 60}:{m % 60:02d}+1" if m else "0:00+1"
    return f"{m // 60}:{m % 60:02d}"


def write_result(path, dates, E, c, d, s0, s1, price, g=None, E_adj=None,
                 price_mat=None, extra_sheets=()):
    """写出结果文件（工作表名与模板一致）。"""
    sheets = {"计划购电量": plan_sheet_frame(dates, E, price, price_mat)}
    if E_adj is not None:
        sheets["调整购电量"] = plan_sheet_frame(dates, E_adj, price, price_mat)
    sheets["充放电量"] = soc_sheet_frame(dates, c, d, s0, s1)
    sheets["紧急购电量"] = emergency_frame(dates, g if g is not None else np.zeros_like(E))
    order = ["计划购电量"] + (["调整购电量"] if E_adj is not None else []) + \
            ["充放电量", "紧急购电量"]
    with pd.ExcelWriter(path) as w:
        for k in order:
            sheets[k].to_excel(w, sheet_name=k, index=False)
    return path
