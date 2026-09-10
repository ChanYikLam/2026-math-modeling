# code/ —— 全部源程序目录（唯一真源）

> 本目录 = `C题代码/code/`，是 C 题**全部源程序**的唯一存放处，也是论文附录 E
> 自动引入的对象。目录口径见 `../docs/00_代码目录与命名规范.md`（唯一权威）。

## 与论文的连接方式

`论文/code` 是指向本目录的**软链接**（`论文/code -> ../C题代码/code`），因此：

- 在本目录新建/修改文件，**论文附录立即就是最新内容**，不需要复制、不存在两份副本；
- `论文/sections/90_appendix.tex` 中的 `\codefile{xxx.py}` 逐字对应本目录文件名；
- LaTeX 侧路径始终是 ASCII 的 `code/xxx.py`（中文目录名不进 TeX，无编码风险）；
- `论文/tools/check_paper.py` 经软链接核对文件是否存在。

⚠️ **不要**把 `论文/code` 删掉重建为普通目录——那会造成两份副本并开始漂移。

## 文件清单（24 个）

```text
code/
├── config.py                          口径与参数（全文唯一口径来源）★
├── data_loader.py                     附件读取 + ffill + 时标对齐 + 断言
├── scenario_gen.py                    场景生成、削减与三层保真检验
├── model_q1.py                        问题 1：确定性 LP
├── model_q2.py                        问题 2：两阶段随机规划（紧急购电 5p）
├── model_q3.py                        问题 3：多阶段滚动 + 非预期性（1.5p / 0.5p）
├── model_q4.py                        问题 4：波动电价 + 风险度量
├── exp_newsboy.py                     对照：报童理论分位数 vs 数值覆盖率
├── exp_voi.py                         对照：信息价值 VoI 与预报频次扫描
├── exp_ablation.py                    消融矩阵（共用同一固定场景集）
├── exp_sensitivity.py                 全局敏感性（Sobol 指数）
├── certify.py                         最优性证书（阈值律与互补松弛校验）
├── audit.py                           独立复算费用与物理量（不共用建模费用函数）★
├── plot_style.py                      全局样式与配色语义
├── plot_fig03_q1_dual_price.py        八张数据图的生成脚本，
├── plot_fig04_q1_marginal_value.py      脚本名 = "plot_" + 图文件名（去 .pdf）
├── plot_fig05_waterfall.py
├── plot_fig06_voi_curve.py
├── plot_fig07_ablation_matrix.py
├── plot_fig08_risk_frontier.py
├── plot_fig09_forecast_error.py
├── plot_fig10_strategy_mechanism.py
├── run_all.py                         一键复现全部结果 ★
└── requirements.txt                   依赖清单（锁定确切版本号，不写 >= 区间）
```

> 图 1（决策时序）、图 2（问题依赖）为 TikZ，源文件在 `论文/figures/fig01_timeline.tex`、
> `fig02_dependency.tex`，**没有对应的 Python 脚本**。

## 约定

- **附录会自动原样引入本目录下的真实文件**（`\lstinputlisting`），
  所以**不要**把代码截图贴进附录，也不要写空壳函数——附录内容永远等于这里的文件；
- 文件不存在时，附录中显示红色【缺文件】提示框，编译不会中断，
  但 `论文/tools/check_paper.py` 会报**失败**（格式规范第五条：缺少必要源程序可能被取消评奖资格）；
- **禁止依赖当前工作目录的裸路径**：一切路径从 `config.py` 用 `__file__` 推导，
  这样"从仓库根运行"和"从 `C题代码/` 运行"两种方式都能跑通（规范 §3）；
- 源程序中的中文注释可以正常排版——`preamble.tex` 的 `\lstset` 已把代码清单的中文字体
  指向已嵌入的中文字族；**若你的注释里出现方框或缺字，请检查是否误删了 `basicstyle` 中的 `\songti`**；
- 单行不要过长（>100 字符建议手工换行），虽然 `breaklines=true` 会自动折行，
  但手工换行的代码在纸质版上更好读。

## 命名与提交

- 本目录内容会随 `support.zip` 一起提交，**目录中不得出现任何身份信息**
  （学校、队号、姓名、赛区），包括代码注释与文件头；
- 建议每个文件开头写：用途、输入、输出、运行方式，不要写作者信息；
- **新增文件必须同步补进 `论文/sections/90_appendix.tex` 的 `\codefile{...}` 清单**，
  否则"论文未列全部源程序"属于格式规范第五条风险。
