#!/usr/bin/env bash
# =============================================================================
#  build.sh —— 编译 C 题论文
#  用法：
#     ./build.sh              # 正常编译（自动选择可用引擎）
#     ./build.sh clean        # 清理中间文件
#     ./build.sh check        # 编译后运行提交前合规自查
#
#  支持的引擎（按优先级自动探测）：
#     1) latexmk + xelatex   （TeX Live / MacTeX 完整安装，推荐）
#     2) xelatex             （直接调用，自动连编两遍）
#     3) tectonic            （自带宏包下载；需要网络，首次编译较慢）
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

JOB="main"
BUILD_DIR="build"
mkdir -p "$BUILD_DIR"

clean() {
  rm -rf "$BUILD_DIR"/*.aux "$BUILD_DIR"/*.log "$BUILD_DIR"/*.out \
         "$BUILD_DIR"/*.toc "$BUILD_DIR"/*.fls "$BUILD_DIR"/*.fdb_latexmk
  echo "已清理中间文件"
}

compile_latexmk() {
  echo ">>> 使用 latexmk + xelatex 编译"
  latexmk -xelatex -interaction=nonstopmode -halt-on-error \
          -outdir="$BUILD_DIR" "$JOB.tex"
  cp -f "$BUILD_DIR/$JOB.pdf" "$JOB.pdf"
}

compile_xelatex() {
  echo ">>> 使用 xelatex 编译（连编两遍）"
  xelatex -interaction=nonstopmode -halt-on-error -output-directory="$BUILD_DIR" "$JOB.tex"
  xelatex -interaction=nonstopmode -halt-on-error -output-directory="$BUILD_DIR" "$JOB.tex"
  cp -f "$BUILD_DIR/$JOB.pdf" "$JOB.pdf"
}

compile_tectonic() {
  echo ">>> 使用 tectonic 编译"
  # tectonic 默认把缓存写到 ~/Library/Caches，受限环境下会失败，故显式指定可写目录
  export TECTONIC_CACHE_DIR="${TECTONIC_CACHE_DIR:-$PWD/$BUILD_DIR/.tectonic-cache}"
  tectonic -X compile "$JOB.tex" --outdir "$BUILD_DIR" \
    --keep-intermediates --keep-logs
  cp -f "$BUILD_DIR/$JOB.pdf" "$JOB.pdf"
}

case "${1:-build}" in
  clean) clean; exit 0 ;;
  build|check) ;;
  *) echo "未知参数：$1（可用：build / clean / check）"; exit 2 ;;
esac

if command -v latexmk >/dev/null 2>&1 && command -v xelatex >/dev/null 2>&1; then
  compile_latexmk
elif command -v xelatex >/dev/null 2>&1; then
  compile_xelatex
elif command -v tectonic >/dev/null 2>&1; then
  compile_tectonic
else
  echo "错误：未找到 xelatex / latexmk / tectonic，请先安装 TeX Live（含 ctex 宏包）" >&2
  exit 1
fi

echo
echo "编译完成：$JOB.pdf"
if command -v pdfinfo >/dev/null 2>&1; then
  PAGES=$(pdfinfo "$JOB.pdf" | awk '/^Pages:/{print $2}')
  SIZE=$(du -h "$JOB.pdf" | cut -f1)
  echo "总页数：$PAGES （含摘要页与附录；正文页数上限 30 页，附录页数不限）"
  echo "文件大小：$SIZE （电子版上限 20 MB）"
fi

if [ "${1:-build}" = "check" ]; then
  echo
  python3 tools/check_paper.py
fi
