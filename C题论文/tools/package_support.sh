#!/usr/bin/env bash
# =============================================================================
#  package_support.sh —— 生成支撑材料压缩包 support.zip
#  用法：./tools/package_support.sh
#  内容：main.tex/appendix.tex/full.tex/preamble.tex/build.sh、sections/ 全部 tex、tools/ 三个自查脚本、
#        code/ 全部源程序（23 个）、results/ 五个结果文件、figures/ 全部图（含 v2 新增 5 张）、
#        intermediate/ 的汇总与审计类结果、notes/ 数值台账与交底书、README.md
#  不含：逐日解转储的大体积 JSON（run_all.py 可重建，附录 A 已声明）
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="support.zip"
STAGE="build/support"
rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE"

cp -R code "$STAGE/code"
mkdir -p "$STAGE/results" "$STAGE/figures" "$STAGE/intermediate" "$STAGE/notes" \
         "$STAGE/sections" "$STAGE/tools"
cp results/*.xlsx "$STAGE/results/"
cp figures/*.pdf "$STAGE/figures/"
cp README.md "$STAGE/README.md"
cp notes/数值台账.md notes/写作交底.md notes/v2升级说明.md "$STAGE/notes/" 2>/dev/null || true

# 论文源文件与工程脚本（附录 A 的文件清单承诺包含，故必须随包）
cp main.tex appendix.tex full.tex preamble.tex build.sh "$STAGE/" 2>/dev/null || true
cp sections/*.tex "$STAGE/sections/" 2>/dev/null || true
cp tools/check_paper.py tools/check_numbers.py tools/verify_ref.py \
   tools/package_support.sh "$STAGE/tools/" 2>/dev/null || true

# 中间结果：只带汇总与审计类（逐日解转储体积大，run_all.py 可重建）
for f in audit.json audit_report.md paper_numbers.json exp_scan.json exp_sobol.json \
         exp_na.json exp_benchmark.json q4_cvar.json q4_price.json window_aggregates.json \
         exp_oos.json q2_margin.json q1_dual2.json results_summary.json \
         exp_copula.json exp_chance.json exp_dro.json decomp.json exp_loaderr.json; do
  [ -f "intermediate/$f" ] && cp "intermediate/$f" "$STAGE/intermediate/" || true
done
cp intermediate/q1.json "$STAGE/intermediate/" 2>/dev/null || true

# 清理缓存与临时文件
find "$STAGE" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name ".DS_Store" -delete 2>/dev/null || true
rm -rf "$STAGE/code/__pycache__"

( cd "$STAGE" && zip -qr "../../${OUT}" . )
SZ=$(du -h "${OUT}" | cut -f1)
echo "已生成 ${OUT} 大小 ${SZ}（上限 20 MB）"
unzip -l "${OUT}" | tail -3
