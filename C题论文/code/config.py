# -*- coding: utf-8 -*-
"""
C 题公共配置与数据管道（唯一口径源）
====================================
本文件是全论文**唯一**的口径定义源（对应写作需求 D2 口径纪律）。
论文正文引用口径编号 C-01…C-08，不另行手写求和式。

时标口径（陷阱 A，见 C题知识点解析/01 §4）
----------------------------------------
附件 1/2/4 的时刻标签是**时段末端**，共 144 个标签，覆盖一天的 144 个 10 min 区间。
本文件采用**位置读法**：第 j 个槽位（j 从 0 开始）= [j*10min, (j+1)*10min)，
对应附件第 j+1 个数据行/列。附件标签仅作显示，**不按标签重映射**。
- 附件标签 "10:10" → 槽位 j = 60 = [10:00, 10:10)
- 论文表 1 的 "10:00-10:10" 即取该槽位。

单位口径
--------
附件 1/2/3 的负载与光伏为 **kW**；附件 1/4 的电价为 **元/kWh**；
本模型全部决策变量为**电量（kWh）**，故 E = P * DT，DT = 1/6 h。
充放电功率上限 5000 kW → 电量上限 5000 * DT = 833.3333 kWh/槽。

口径编号（与论文《写作交底》§6.1 完全一致，附录 E 原样引入本文件）
-----------------------------------------------------------------
C-01 无储能基线购电费 C^base | C-02 全天购电量 | C-03 总购电费用（计划 + 紧急 + 调整相关）
C-04 节省率 | C-05 紧急购电量 | C-06 弃光/盈余处置电量 | C-07 充放电量与储电量（交流侧）
C-08 储电量递推与终端条件 | C-09 调整与违约费用 | C-10 信息价值 VoI | C-11 条件风险价值 CVaR

假设编号：A1 不允许售电 | A2 单边效率 0.9 | A3 不同时充放 | A4 忽略自放电与循环衰减
A5 跨日 SOC 连续递推 | A6 每日终端 S_144 >= S_0 | A7 调整决策后覆盖前 | A8 1 月为预热期
A9 信息结构取 R3 | A10 波动电价下 0:00 可用电价预报 = 分时骨架
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
PAPER_DIR = os.path.dirname(HERE)                       # C题论文/
WORKSPACE = os.path.dirname(PAPER_DIR)                  # 工作区根
PROBLEM_DIR = os.path.join(WORKSPACE, "CUMCM2026Problems(1)", "C题")
ATTACH_DIR = os.path.join(PROBLEM_DIR, "附件")
TEMPLATE_DIR = os.path.join(ATTACH_DIR, "附件5")
RESULT_DIR = os.path.join(PAPER_DIR, "results")
INTERMEDIATE_DIR = os.path.join(PAPER_DIR, "intermediate")
FIGURE_DIR = os.path.join(PAPER_DIR, "figures")

for _d in (RESULT_DIR, INTERMEDIATE_DIR, FIGURE_DIR):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# 物理参数（题面附录 1）
# --------------------------------------------------------------------------
DT = 1.0 / 6.0              # h，单个 10 min 槽时长
N_SLOT = 144                # 一天 144 个 10 min 槽
ETA_C = 0.9                 # 充电效率
ETA_D = 0.9                 # 放电效率
S_MAX = 10800.0             # kWh，储电量上限
S_MIN = 1200.0              # kWh，储电量下限
P_MAX = 5000.0              # kW，最大充放电功率
E_MAX = P_MAX * DT          # kWh，单槽充/放电量上限 833.3333
S_INIT = 6000.0             # kWh，2025-01-01 00:00 储电量
EMERGENCY_MULT = 5.0        # 紧急购电电价倍数
BREACH_MULT = 0.5           # 计划 > 调整：违约电价倍数
EXCESS_MULT = 1.5           # 调整 > 计划：超出部分电价倍数

# 结果窗口（问题 2/3/4）：2025-02-01 至 2025-12-31，334 天
WIN_START = "2025-02-01"
WIN_END = "2025-12-31"
WARMUP_START = "2025-01-01"

# 四个指定日期（表 3 / 问题 2、3、4 的结果表）
KEY_DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]

# 充放电量表的时间段划分（表 2）
BLOCKS = [(0, 24), (24, 48), (48, 72), (72, 96), (96, 120), (120, 144)]
BLOCK_LABELS = ["0:00-4:00", "4:00-8:00", "8:00-12:00",
                "12:00-16:00", "16:00-20:00", "20:00-24:00"]

# 表 1 指定的 6 个 10 min 时段 -> 槽位下标（0 基）
TABLE1_SLOTS = [("10:00-10:10", 60), ("12:00-12:10", 72), ("14:00-14:10", 84),
                ("16:00-16:10", 96), ("18:00-18:10", 108), ("20:00-20:10", 120)]

# 调整（预报）时刻 -> 控制窗口起始槽位
FORECAST_HOURS = [0, 6, 12, 18]
EPOCH_SLOT = {h: h * 6 for h in FORECAST_HOURS}   # 0, 36, 72, 108


def slot_label(j: int) -> str:
    """槽位 -> 附件标签（时段末端）。"""
    m = (j + 1) * 10
    if m == 1440:
        return "0:00+1"
    return f"{m // 60}:{m % 60:02d}"


# --------------------------------------------------------------------------
# 数据读取
# --------------------------------------------------------------------------
def read_attachment1() -> pd.DataFrame:
    """附件 1：典型日 {电价 元/kWh, 小区负载 kW, 光伏发电预测功率 kW}，144 槽。"""
    df = pd.read_excel(os.path.join(ATTACH_DIR, "附件1.xlsx"), header=0)
    df.columns = ["时间", "price", "load", "pv"]
    assert len(df) == N_SLOT, len(df)
    return df


def read_attachment2() -> tuple[pd.DataFrame, pd.DataFrame]:
    """附件 2：2025 全年逐日逐槽 {小区负载 kW, 光伏发电实际功率 kW}。"""
    load = pd.read_excel(os.path.join(ATTACH_DIR, "附件2.xlsx"), sheet_name="小区负载", header=0)
    pv = pd.read_excel(os.path.join(ATTACH_DIR, "附件2.xlsx"), sheet_name="光伏发电实际功率", header=0)
    out = []
    for df, name in ((load, "load"), (pv, "pv")):
        df = df.rename(columns={df.columns[0]: "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.set_index("date")
        df.columns = [f"s{j}" for j in range(N_SLOT)]
        df = df.astype(float)
        out.append(df)
    return out[0], out[1]


def read_attachment3() -> pd.DataFrame:
    """附件 3：每天 0:00/6:00/12:00/18:00 发布的未来 24 h 整点光伏预报（kW）。

    返回长表：index=(date, hour)，columns=lead1..lead24（lead k 对应 [h0+k-1, h0+k)）。
    """
    df = pd.read_excel(os.path.join(ATTACH_DIR, "附件3.xlsx"), header=0)
    df.columns = ["date", "hour"] + [f"lead{k}" for k in range(1, 25)]
    df["date"] = df["date"].ffill()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["hour"] = df["hour"].astype(str).str.strip()
    df["hour"] = df["hour"].map(lambda s: int(s.split(":")[0]))
    for k in range(1, 25):
        df[f"lead{k}"] = pd.to_numeric(df[f"lead{k}"], errors="coerce")
    return df.set_index(["date", "hour"]).sort_index()


def read_attachment4() -> pd.DataFrame:
    """附件 4：2025 全年逐日逐槽实时电价（元/kWh）。"""
    df = pd.read_excel(os.path.join(ATTACH_DIR, "附件4.xlsx"), header=0)
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.set_index("date")
    df.columns = [f"s{j}" for j in range(N_SLOT)]
    return df.astype(float)


def read_template(sheet: str, fname: str = "result2.xlsx", nrows: int | None = None):
    """读取附件 5 的结果模板（用于比对结构）。"""
    return pd.read_excel(os.path.join(TEMPLATE_DIR, fname), sheet_name=sheet,
                         header=None, nrows=nrows)


@dataclass
class Panel:
    """按槽位展开的全年面板数据。"""
    dates: pd.DatetimeIndex

    def __post_init__(self):
        self.load, self.pv = read_attachment2()
        self.price_fixed = read_attachment1().set_index("时间")[["price", "load", "pv"]]
        self.price_flat = read_attachment4()
        self.pf3 = read_attachment3()

    # ---- 逐槽矩阵（行=日期，列=槽位）----
    def L(self, dates=None) -> pd.DataFrame:
        return self.load if dates is None else self.load.loc[dates]

    def PV(self, dates=None) -> pd.DataFrame:
        return self.pv if dates is None else self.pv.loc[dates]

    def P(self, dates=None, volatile: bool = False) -> pd.DataFrame:
        """电价矩阵：volatile=False 用附件 1 固定价（每天相同），True 用附件 4。"""
        dates = self.load.index if dates is None else pd.DatetimeIndex(dates)
        if volatile:
            return self.price_flat.loc[dates]
        row = read_attachment1()["price"].to_numpy()
        return pd.DataFrame(np.tile(row, (len(dates), 1)), index=dates,
                            columns=[f"s{j}" for j in range(N_SLOT)])

    # ---- 预报 ----
    def pv_forecast(self, date, hour: int) -> np.ndarray:
        """取 date 日 hour 时刻发布的 24 h 光伏预报，展开为 144 槽（每整点 6 槽）。"""
        row = self.pf3.loc[(pd.Timestamp(date).normalize(), hour)]
        hourly = np.array([row[f"lead{k}"] for k in range(1, 25)], dtype=float)
        return np.repeat(hourly, 6)


# --------------------------------------------------------------------------
# 口径指标（C-01…C-08）
# --------------------------------------------------------------------------
def baseline_cost(p_price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> float:
    """C-01 无储能基线购电费：C^base = sum_t p_t * max(L_t - PV_t, 0) * DT。"""
    return float(np.sum(p_price * np.maximum(load - pv, 0.0) * DT))


def curtailment(price, load, pv, E, c, d) -> np.ndarray:
    """C-05 逐槽弃光/盈余电量：s_t = PV*DT + E + d - L*DT - c（应 >= 0）。"""
    return pv * DT + E + d - load * DT - c
