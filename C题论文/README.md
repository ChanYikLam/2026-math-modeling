# C 题《微网与外部电网电力调控策略》——论文与复现工程

> 本文件夹是 **2026 高教社杯全国大学生数学建模竞赛 C 题**的**独立完整交付**：
> 一套可编译的论文（LaTeX）、一套可从原始附件重算出论文每一个数字的源程序、
> 五个结果文件、全部矢量图与独立审计报告。
>
> 与仓库中 `论文/`（写作模板）的区别：`论文/` 是空骨架（417 处占位符），
> 本文件夹是**已完成的论文**——所有数字都由 `code/` 下的程序从 `附件 1–4` 重新算出，
> 论文正文与结果文件逐格一致。

---

## 一、交付物

| 交付物 | 路径 | 说明 |
|---|---|---|
| 参赛论文（PDF） | `main.pdf` | 摘要页 + 正文（≤30 页）+ 参考文献 + 附录 A–H，单文件、无目录、无身份信息 |
| LaTeX 源文件 | `main.tex` `preamble.tex` `sections/` | 可重新编译 |
| 源程序 | `code/` | 12 个 Python 脚本，一键复现 `python3 code/run_all.py` |
| 结果文件 | `results/` | `result1.xlsx` `result2.xlsx` `result3.xlsx` `result4-2.xlsx` `result4-3.xlsx` |
| 矢量图 | `figures/` | 图 1/2 为 TikZ，图 3–10 为矢量 PDF |
| 中间结果 | `intermediate/` | 全部求解输出 JSON + 独立审计报告 |
| 数值台账 | `notes/数值台账.md` `intermediate/paper_numbers.json` | 论文每个数字的出处 |
| 写作交底 | `notes/写作交底.md` | 口径与模型的唯一权威说明 |
| 上游文档蒸馏 | `notes/A…E_*.md` | 由题面/知识点/验证/炫技/行业文档蒸馏 |

## 二、三分钟复现

```bash
cd code
python3 -m pip install -r requirements.txt     # numpy/pandas/scipy/openpyxl/matplotlib/scikit-learn
python3 run_all.py                             # 约 5 分钟，生成全部结果文件与中间结果
python3 audit.py                               # 独立审计 A1–A10（从结果文件复算）
python3 paper_numbers.py                       # 汇总论文数值台账
```

编译论文（需要 XeLaTeX 或 tectonic）：

```bash
./build.sh                 # 自动探测 latexmk+xelatex / xelatex / tectonic，产出 main.pdf
touch final.flag && ./build.sh && python3 tools/check_paper.py --strict   # 定稿模式 + 合规自查
```

## 三、核心结论（全部由 `code/` 复算）

| 模型 | 总费用（元） | 相对无储能基线节省 | 紧急购电量（kWh） |
|---|---:|---:|---:|
| 问题 1（典型日确定性 LP） | 35 126.95 | 26.90% | — |
| 问题 2（固定价两阶段随机规划） | 14 264 792.13 | 13.06% | 172 015.82 |
| 问题 3（固定价四次滚动调整） | 13 932 402.95 | 15.08% | 64 522.09 |
| 问题 4-2（波动电价两阶段） | 15 094 255.84 | 11.35% | 182 759.86 |
| 问题 4-3（波动电价四次滚动） | 14 722 153.17 | 13.54% | 63 523.11 |

- **信息价值**：4 次预报相对 1 次节省 332 389.18 元（2.33%），已实现完全信息上界价值的 85.1%，再加密最多再省 0.42% → 不建议继续加密；
- **瓶颈**：容量摆幅是主要瓶颈（解除容量上限可再省 22.1%），充放电功率在部分时段同时构成约束（解除后仅再省 1.7%）；
- **套利条件**：峰谷价比高于 1/(\eta_c\eta_d)=1.2346 时有利。

## 四、目录结构

```
C题论文/
├── main.tex  preamble.tex  build.sh  main.pdf
├── sections/            摘要 + 正文十章 + 参考文献 + 附录 A–H
├── figures/             fig01/fig02（TikZ）+ fig03–fig10（矢量 PDF）
├── code/                全部源程序（config/lp_engine/q1–q4/results_io/exp_scan/exp_sobol/audit/paper_numbers/run_all）
├── results/             五个结果文件
├── intermediate/        求解输出 JSON、审计报告、数值台账 JSON
├── notes/               写作交底、数值台账、上游文档蒸馏稿
└── tools/               check_paper.py（合规自查）、check_numbers.py（数字对拍）
```

---

## 五、定稿状态（实测）

| 项目 | 实测值 | 要求 | 结论 |
|---|---|---|---|
| PDF 总页数 | 88 | — | — |
| 摘要页 | 1 | ≤1 | 合规 |
| 正文（一章至十章） | 29 | ≤30 | 合规 |
| 参考文献 | 1 | — | 合规 |
| 附录 A–J | 57 | 不限 | 合规 |
| 电子版大小 | 1.5 MB | ≤20 MB | 合规 |
| 目录 | 无 | 不得有 | 合规 |
| 身份信息 | 无 | 不得出现 | 合规 |
| 占位符 | 0 | 0 | 合规 |
| 附录源程序 | 16 个文件 | 全部可运行 | 合规 |
| 未定义引用 | 0 | 0 | 合规 |

```text
$ python3 tools/check_paper.py --strict
  结论：全部机械检查通过（0 项注意需人工确认）
$ python3 tools/audit.py          # 独立审计 A1–A10
  供给缺口 3.41e-13 kWh；SOC 递推 1.09e-11 kWh；越界/互斥/负购电 = 0；
  费用复算相对误差 0；交付物块级残差 ≤2.96e-4 kWh（四位小数取整上界 7.0e-4）
```

## 六、复现与对拍

- 一键复现：`python3 code/run_all.py`（约 5 分钟；`--fast` 跳过对照实验）；
- 独立审计：`python3 code/audit.py`（从**结果文件**与原始附件复算，不调用建模费用函数）；
- 数值台账：`python3 code/paper_numbers.py` → `intermediate/paper_numbers.json` 与 `notes/数值台账.md`；
- 支撑材料：`./tools/package_support.sh` → `support.zip`（2.3 MB，52 个文件）。
