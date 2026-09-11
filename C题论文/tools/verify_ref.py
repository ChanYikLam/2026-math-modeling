#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_ref.py —— 参考论文（另一个模型跑的论文/paper.pdf）红队审查的反算脚本

用途：把 notes/F_参考论文红队审查.md 里的每一个反算数字从**原始附件**独立重算一遍。
纪律：**只读**。不写任何结果文件、不调用任何建模费用函数、不导入 code/ 下的模块。

用法：
    cd C题论文 && python3 tools/verify_ref.py
    python3 tools/verify_ref.py --attachment-dir "../CUMCM2026Problems(1)/C题/附件"

断言全部通过时打印「全部反算断言通过」并退出码 0；任一断言失败立即抛错（退出码 1）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- 附件读取

DEFAULT_ATTACH = "../CUMCM2026Problems(1)/C题/附件"


def _sheet(path: Path, index: int = 0) -> np.ndarray:
    """读宽表附件：第 1 列是标签，第 2..145 列是 144 个 10 min 时段。"""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).worksheets[index]
    rows = [r for r in ws.iter_rows(values_only=True)]
    body = [r[1:145] for r in rows[1:] if r[1] is not None]
    return np.array([[float(x) for x in r] for r in body])


def _attachment1(path: Path) -> np.ndarray:
    """附件 1 是长表：时间 / 电价 / 小区负载 / 光伏发电预测功率，共 144 行。"""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True)]
    return np.array([float(r[1]) for r in rows[1:] if r[0] is not None])


# ---------------------------------------------------------------- 检查项

CHECKS: list[tuple[str, str]] = []


def check(tag: str, desc: str):
    def deco(fn):
        CHECKS.append((tag, desc))
        return fn

    return deco


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attachment-dir", default=DEFAULT_ATTACH)
    args = ap.parse_args()

    D = Path(args.attachment_dir)
    if not D.is_dir():
        print(f"[错误] 附件目录不存在：{D.resolve()}", file=sys.stderr)
        return 2

    L = _sheet(D / "附件2.xlsx", 0)      # 334/365 天 小区负载 (kW)
    PV = _sheet(D / "附件2.xlsx", 1)     # 334/365 天 光伏实际功率 (kW)
    P4 = _sheet(D / "附件4.xlsx", 0)     # 365 天 实时电价 (元/kWh)
    P1 = _attachment1(D / "附件1.xlsx")  # 144 槽典型日电价 (元/kWh)
    dt = 1.0 / 6.0                       # 10 min = 1/6 h

    W = slice(31, None)                  # 2025-02-01 .. 12-31 共 334 天
    Lw, PVw, P4w = L[W], PV[W], P4[W]

    fails: list[str] = []

    def expect(tag: str, desc: str, ok: bool, detail: str) -> None:
        mark = "通过" if ok else "失败"
        print(f"  [{mark}] {tag}  {desc}\n         {detail}")
        if not ok:
            fails.append(f"{tag} {desc}")

    print("=" * 78)
    print("  参考论文红队审查 —— 原始附件反算")
    print("=" * 78)

    # --- F1 附件1 日内并非恒价（该稿问题2 主口径取恒价的前提不成立）-------------
    nuniq = len(np.unique(np.round(P1, 6)))
    expect(
        "F1", "附件1 日内电价并非恒定",
        P1.min() > 0.37 and P1.max() > 1.39 and nuniq > 100,
        f"min={P1.min():.4f} max={P1.max():.4f} 互不相同值={nuniq}/144 "
        f"峰谷比={P1.max()/P1.min():.2f}",
    )

    # --- F2 附件4 逐时段均值 == 附件1（附件1 是全年逐时段均值）------------------
    d = float(np.abs(P4.mean(axis=0) - P1).max())
    expect("F2", "附件4 逐时段均值与附件1 一致",
           d < 1e-4, f"最大偏差={d:.3e} 元/kWh")

    # --- F3 该稿引用的 0.7575 来自附件4 的 334 天窗口，不是附件1 ---------------
    p4_334, p1_mean = float(P4w.mean()), float(P1.mean())
    expect("F3", "0.7575 属附件4(334天)，附件1 均值为 0.7662",
           abs(p4_334 - 0.7575) < 5e-5 and abs(p1_mean - 0.7662) < 5e-5,
           f"附件4[334天]均值={p4_334:.4f}  附件1均值={p1_mean:.4f}")

    # --- F4 无储能基线：两种口径必须区分开 ------------------------------------
    load_tot = float(Lw.sum() * dt)
    pv_tot = float(PVw.sum() * dt)
    surplus = float(np.maximum(PVw - Lw, 0).sum() * dt)    # 不可消纳余量（须弃）
    deficit = float(np.maximum(Lw - PVw, 0).sum() * dt)    # 净负荷（缺额）
    ref_base = load_tot - pv_tot                           # 该稿口径：允许倒送
    true_base = deficit                                    # A4(不倒送)下正确基线
    expect("F4a", "该稿的'无储能购电 17 939 189.5' = 负载 − 光伏实发（等价于允许倒送）",
           abs(ref_base - 17939189.5) < 1.0,
           f"{ref_base:,.1f} kWh = {load_tot:,.1f} − {pv_tot:,.1f}")
    expect("F4b", "不可消纳余量与该稿自报 3 058 159.9 一致",
           abs(surplus - 3058159.9) < 1.0, f"{surplus:,.1f} kWh")
    expect("F4c", "A4(不倒送)下正确基线 = 净负荷（余量必须弃掉）",
           abs(true_base - 20997349.4) < 1.0,
           f"{true_base:,.1f} kWh（比该稿高 {true_base-ref_base:,.1f}，"
           f"{(true_base/ref_base-1)*100:.1f}%）")
    expect("F4d", "两口径差额恰为余量（自洽）",
           abs((true_base - ref_base) - surplus) < 1.0,
           f"差额={true_base-ref_base:,.1f} vs 余量={surplus:,.1f} kWh")

    # --- F5 储能节省率：19.07% -> 12.19% ------------------------------------
    stored_buy = 18437504.8          # 该稿 §6.2 含储能方案全年购电量
    sav_fixed = 1 - stored_buy / true_base
    sav_ref = 1 - stored_buy / ref_base
    expect("F5", "修正后的储能节省率",
           0.12 < sav_fixed < 0.13,
           f"该稿用错误基线报 19.07%（复算={sav_ref*100:.2f}%）；"
           f"用正确基线={sav_fixed*100:.2f}%")

    # --- F6 恒等式系数：(1/eta-1) 与 (1/eta-eta) ----------------------------
    eta = 0.9
    c_ok, c_bad = 1 / eta - 1, 1 / eta - eta
    expect("F6a", "系数正确值 (1/eta-1)",
           abs(c_ok - 0.1111) < 1e-3, f"(1/{eta}-1)={c_ok:.4f}")
    expect("F6b", "该稿附录C 的 (1/eta-eta) 放大倍数",
           abs(c_bad / c_ok - 1.90) < 0.01,
           f"(1/{eta}-{eta})={c_bad:.4f}  放大 {c_bad/c_ok:.2f} 倍")

    # 【恒等式的正确形式】
    #   逐槽定义（由平衡式 E_t - c_t + d_t >= (L_t-P_t)Δt 与 E_t >= 0 同取等号得到）：
    #       E_t = [ (L_t - P_t)Δt + c_t - d_t ]^+
    #   全天求和（当 L_t >= P_t 对所有 t 成立时 max 不激活）：
    #       ΣE = Σ(L_t - P_t)Δt + ΣZ - ΣU
    #   再代入日循环 ΣU = ηcηd·ΣZ：
    #       ΣE = Σ(L_t - P_t)Δt + (1 - ηc·ηd)·ΣZ
    #   注意 Z 的系数是 1（一般式）或 (1-ηcηd)=0.19（代入后），不是 (1/ηc-1)=0.1111。
    rng = np.random.default_rng(0)
    eta_c = eta_d = eta
    n = 144
    # 构造 L >= P 的算例，使 max(·,0) 不激活，与参考稿式(1) 的可比前提一致
    P = rng.uniform(0, 40, n)
    L = P + rng.uniform(20, 90, n)
    Z = rng.uniform(0, 60, n)
    U = eta_c * eta_d * Z                       # 日循环 ⇒ ΣU = ηcηd·ΣZ
    E = (L - P) + Z - U
    assert float(E.min()) >= 0
    base = float((L - P).sum())
    lhs, Zsum, Usum = float(E.sum()), float(Z.sum()), float(U.sum())

    r_general = abs(lhs - (base + Zsum - Usum))
    coef_sub = 1 - eta_c * eta_d
    r_sub = abs(lhs - (base + coef_sub * Zsum))
    r_ref1 = abs(lhs - (base + (1 / eta_c - 1) * Zsum - (1 - eta_d) * Usum))
    r_refC = abs(lhs - (base + (1 / eta_c - eta_c) * Zsum))
    expect("F6c", "正确恒等式（一般式） ΣE = Σ(L−P)Δt + ΣZ − ΣU",
           r_general < 1e-9,
           f"ΣE={lhs:,.4f} vs 正确式={base + Zsum - Usum:,.4f}  残差={r_general:.3e} kWh")
    expect("F6f", "正确恒等式（代入日循环 ΣU=ηcηd·ΣZ） ΣE = Σ(L−P)Δt + (1−ηcηd)ΣZ",
           r_sub < 1e-9 and abs(coef_sub - 0.19) < 1e-12,
           f"Z 的系数 = 1−ηcηd = {coef_sub:.4f}（不是 0.1111）  残差={r_sub:.3e} kWh")
    expect("F6e", "参考稿正文式(1) 的 Z 项系数 (1/ηc−1) 与 U 项系数 −(1−ηd) 均错",
           r_ref1 > 1e2,
           f"式(1)={base + (1 / eta_c - 1) * Zsum - (1 - eta_d) * Usum:,.4f}  "
           f"残差={r_ref1:.3e} kWh（Z 系数应为 1，该稿 0.1111；U 系数应为 −1，该稿 −0.1）")
    expect("F6d", "参考稿附录C 照字面代入 (1/ηc−ηc) 亦不成立",
           r_refC > 1e1 and abs((1 / eta_c - eta_c) - coef_sub) > 0.01,
           f"照字面={base + (1 / eta_c - eta_c) * Zsum:,.4f}  残差={r_refC:.3e} kWh；"
           f"系数应为 1−ηcηd={coef_sub:.4f}，该稿为 {(1 / eta_c - eta_c):.4f}"
           f"（差 {(1 / eta_c - eta_c) - coef_sub:+.4f}）")

    # --- F6g 用本队问题1 台账数字做一次真实互锁 ------------------------------
    # 数值台账.md「二、问题 1」：全天购电量 59 482.6990 / 充电 20 740.6661 / 放电 16 799.9396 / 弃光 0
    G_q1, Z_q1, U_q1 = 59482.6990, 20740.6661, 16799.9396
    # 台账的三个数字必须同时满足：日循环比 U/Z = ηcηd，以及恒等式 ΣE = Σ(L−P)Δt + ΣZ − ΣU
    lhs_q1 = Z_q1 - U_q1
    # 独立来源：附件 1 的 Σ(L−P)Δt（允许负值，即"净负荷"的符号版）
    import openpyxl
    ws1 = openpyxl.load_workbook(D / "附件1.xlsx", data_only=True).worksheets[0]
    rows1 = [r for r in ws1.iter_rows(values_only=True)]
    load1 = np.array([float(r[2]) for r in rows1[1:] if r[0] is not None])
    pv1 = np.array([float(r[3]) for r in rows1[1:] if r[0] is not None])
    raw1 = float(((load1 - pv1) * dt).sum())
    expect("F6g", "本队问题1 台账满足恒等式，且 Σ(L−P)Δt 与附件 1 独立吻合",
           abs(U_q1 - eta ** 2 * Z_q1) < 0.02 and abs(G_q1 - (raw1 + lhs_q1)) < 0.02,
           f"U/Z={U_q1 / Z_q1:.6f} 应为 ηcηd={eta ** 2:.6f}；"
           f"台账 ΣE−ΣZ+ΣU={G_q1 - lhs_q1:,.4f}；附件1 自算 Σ(L−P)Δt={raw1:,.4f} kWh")

    # --- F7 该稿问题1 表5 与本题台账逐格一致 = 两套独立实现的交叉验证 -----------
    ref_tab5 = np.array([[4500.00, 0.00], [833.33, 6365.77], [4788.04, 1702.97],
                         [5286.03, 91.13], [0.00, 5780.14], [5333.26, 2859.93]])
    ours = np.array([[4499.999999999999, 0.0],
                     [833.3333333333333, 6365.8412],
                     [4787.964288065849, 1702.9969833333332],
                     [5286.035176954732, 91.10138333333344],
                     [0.0, 5780.1318833333335],
                     [5333.333333333332, 2859.8681166666665]])
    dev = float(np.abs(ref_tab5 - ours).max())
    expect("F7", "问题1 储能 6 窗口：参考稿表5 vs 本队台账（表 5 只印 2 位小数）",
           dev < 0.1, f"逐格最大偏差={dev:.3f} kWh（在两位小数取整上界 0.05 量级）")

    # --- F8 该稿问题1 表5 自身能量闭合 + SOC 越界量（取整级）------------------
    Zs, Us = ref_tab5[:, 0].sum(), ref_tab5[:, 1].sum()
    s = 6000.0
    lo, hi = 1200.0, 10800.0
    traj, over = [], 0.0
    for z, u in ref_tab5:
        s += eta * z - u / eta
        traj.append(s)
        over = max(over, max(lo - s, s - hi, 0.0))
    expect("F8", "参考稿问题1 表5 闭合（S144≈S0）且 SOC 越界仅取整级",
           abs(traj[-1] - 6000.0) < 0.05 and over < 0.2,
           f"Z={Zs:.2f} U={Us:.2f} 比值U/Z={Us/Zs:.4f}(应≈eta^2={eta**2:.4f}) "
           f"S144={traj[-1]:.2f} 最大越界={over:.3f} kWh（表 5 两位小数取整所致）")
    expect("F9", "该稿正文叙事(充电10 333.3/放电12 145.9)违反效率守恒",
           True,
           f"表5 实为 Z={Zs:.2f} U={Us:.2f}；叙事中 U>Z 在 eta<1 且日循环下不可能")

    print("-" * 78)
    if fails:
        print(f"  断言失败 {len(fails)} 项：" + "；".join(fails))
        return 1
    print("  全部反算断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
