# C题代码/ —— 微网与外部电网电力调控策略 代码工作区

> **当前状态：目录脚手架与目录规范已就绪，尚未编写任何源程序。**
> 各空目录用 `.gitkeep` 占位，以保证 Git 能记录目录结构。
>
> **目录格式与命名的唯一权威**：`docs/00_代码目录与命名规范.md`。
> 本文件只是总览；两者冲突时以规范文件为准。

本目录是 C 题**全部代码的唯一工作区**，目录划分与
`论文/sections/90_appendix.tex` 附录 A 中 `support.zip` 的结构**逐项一致**——
定稿时本目录可直接打包为支撑材料，无需重新整理。

---

## 1. 目录用途

| 目录 | 放什么 | 进 `support.zip` |
|---|---|---|
| `code/` | **全部源程序**（24 个，扁平结构便于 `import`），与论文附录 E 逐字对应 | 是 |
| `data/` | 附件 1–4 只读副本（开发期代码可直接读仓库内原始附件） | 是 |
| `result/` | 五个交付结果文件 `result1/2/3/4-2/4-3.xlsx`（模板见 `附件5/`） | 是 |
| `figures/` | 八张数据图的矢量 PDF | 是 |
| `intermediate/` | `scenarios.npz`、`audit_report.md`、`paper_numbers.json` | 是 |
| `logs/` | 运行日志（已被根 `.gitignore` 的 `*.log` 忽略） | 否 |
| `tests/` | 开发期自检与对拍脚本（论文只提交 `code/audit.py`） | 否 |
| `notebooks/` | 探索性分析（结论须回写 `code/` 才能复现） | 否 |
| `docs/` | 目录规范、数据字典、接口约定 | 否 |

`results_summary.json`（一键复现摘要，`run_all.py` 写出）位于本目录根。

---

## 2. `code/` 文件清单（24 个）

| 组 | 文件 |
|---|---|
| 口径与数据 | `config.py`、`data_loader.py`、`scenario_gen.py` |
| 四个问题模型 | `model_q1.py`、`model_q2.py`、`model_q3.py`、`model_q4.py` |
| 对照与实验 | `exp_newsboy.py`、`exp_voi.py`、`exp_ablation.py`、`exp_sensitivity.py` |
| 证书与审计 | `certify.py`、`audit.py`（`audit.py check-paper` 做论文数字对拍） |
| 绘图 | `plot_style.py`、`plot_fig03_q1_dual_price.py` … `plot_fig10_strategy_mechanism.py`（共 9 个） |
| 一键与依赖 | `run_all.py`、`requirements.txt` |

**绘图命名规则**：脚本名 = `plot_` + 图文件名（去 `.pdf`），与 `论文/figures/README.md` 的表逐行对应。
图 1（决策时序图）、图 2（问题依赖图）为 TikZ，源文件在 `论文/figures/`，**没有 Python 脚本**。

> 文件名与附录 `\codefile{...}` **逐字一致**：改名必须同步改
> `论文/sections/90_appendix.tex`，否则附录显示红色【缺文件】，
> `论文/tools/check_paper.py` 会判失败（格式规范第五条）。

---

## 3. 与论文的连接：软链接（零漂移）

```text
论文/code  ->  ../C题代码/code        （软链接，唯一真源）
```

- 论文附录 E 用 `\lstinputlisting` 原样引入 `code/xxx.py`，经软链接即本目录的真实文件；
- **在本目录改动代码，论文附录立即同步**，不需要复制、不存在两份副本；
- LaTeX 侧路径始终是 ASCII 的 `code/xxx.py`，中文目录名不进 TeX，无编码风险；
- ⚠️ **不要**把 `论文/code` 删掉重建为普通目录，否则立刻产生副本并开始漂移。

---

## 4. 运行方式（两种工作目录都必须可用）

```bash
# 方式一：从仓库根
pip install -r C题代码/code/requirements.txt
python C题代码/code/run_all.py
python C题代码/code/audit.py check-paper

# 方式二：从工作区
cd C题代码
pip install -r code/requirements.txt
python code/run_all.py
```

两种方式都能跑通，是因为**一切路径由 `code/config.py` 用 `__file__` 推导**，
不使用依赖 CWD 的裸路径（规范 §3）。附件目录解析顺序：
`MICROGRID_ATTACH` 环境变量 → `C题代码/data/` → 仓库内 `CUMCM2026Problems(1)/C题/附件/` → 抛异常。

---

## 5. 开发约定

1. **单一真源**：常量、口径、时间步长、全部路径只在 `code/config.py` 定义，其他文件一律引用；
2. **禁止身份信息**：本目录随 `support.zip` 提交，注释、文件头、日志中不得出现学校、队号、姓名、赛区；
3. **不写空壳**：附录原样引入真实文件，未实现的功能不建同名文件；
4. **可复现**：随机过程一律走 `CFG.SEEDS` 的显式种子；论文每个数字都要能由 `run_all.py` 复算，
   并写入 `intermediate/paper_numbers.json` 供对拍；
5. **结果文件**：`result/` 下五个 xlsx 的工作表名与列序必须与 `附件5/` 模板一致。

上游依据：`C题炫技方向/13_附录_炫技实现代码骨架.md` §0（已按附件实测校准的时标与口径）、
`C题验证方案/`（L1–L5 验证链与审计阈值）。
