#!/usr/bin/env bash
# =============================================================================
#  build.sh —— 编译 C 题论文
#  用法：
#     ./build.sh              # 编译三个交付物：main.pdf / appendix.pdf / full.pdf
#     ./build.sh main         # 只编正文（main.pdf，≤30 页、不含源程序）
#     ./build.sh appendix     # 只编附录（appendix.pdf，页数不限、含全部源程序）
#     ./build.sh full         # 只编合并版（full.pdf = 正文 + 附录，备用）
#     ./build.sh clean        # 清理中间文件
#     ./build.sh check        # 三个都编 + 运行提交前合规自查
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

compile_latexmk() {          # $1 = job 名（main / appendix / full）
  local job="${1:-$JOB}"
  echo ">>> 使用 latexmk + xelatex 编译 $job"
  # 附录单独编译时要读正文的辅助文件，故附录必须在 main 之后编
  latexmk -xelatex -interaction=nonstopmode -halt-on-error \
          -outdir="$BUILD_DIR" "$job.tex"
  cp -f "$BUILD_DIR/$job.pdf" "$job.pdf"
}

compile_xelatex() {          # $1 = job 名
  local job="${1:-$JOB}"
  echo ">>> 使用 xelatex 编译 $job（连编两遍）"
  xelatex -interaction=nonstopmode -halt-on-error -output-directory="$BUILD_DIR" "$job.tex"
  xelatex -interaction=nonstopmode -halt-on-error -output-directory="$BUILD_DIR" "$job.tex"
  cp -f "$BUILD_DIR/$job.pdf" "$job.pdf"
}

compile_tectonic() {         # $1 = job 名
  local job="${1:-$JOB}"
  echo ">>> 使用 tectonic 编译 $job"
  # tectonic 默认把缓存写到 ~/Library/Caches，受限环境下会失败，故显式指定可写目录
  export TECTONIC_CACHE_DIR="${TECTONIC_CACHE_DIR:-$PWD/$BUILD_DIR/.tectonic-cache}"
  tectonic -X compile "$job.tex" --outdir "$BUILD_DIR" \
    --keep-intermediates --keep-logs
  cp -f "$BUILD_DIR/$job.pdf" "$job.pdf"
}

# 选择一个可用引擎，作为函数 compile_one(job)
if command -v latexmk >/dev/null 2>&1 && command -v xelatex >/dev/null 2>&1; then
  compile_one() { compile_latexmk "$1"; }
elif command -v xelatex >/dev/null 2>&1; then
  compile_one() { compile_xelatex "$1"; }
elif command -v tectonic >/dev/null 2>&1; then
  compile_one() { compile_tectonic "$1"; }
else
  echo "错误：未找到 xelatex / latexmk / tectonic，请先安装 TeX Live（含 ctex 宏包）" >&2
  exit 1
fi

report() {                    # 打印某个交付物的页数与大小
  local f="$1" label="$2"
  [ -f "$f" ] || return 0
  if command -v pdfinfo >/dev/null 2>&1; then
    local pages size
    pages=$(pdfinfo "$f" | awk '/^Pages:/{print $2}')
    size=$(du -h "$f" | cut -f1)
    printf '    %-14s %4s 页  %6s   %s\n' "$f" "$pages" "$size" "$label"
  fi
}

case "${1:-build}" in
  clean) clean; exit 0 ;;
  build)
    # 顺序有依赖：appendix.tex 用 xr 读 build/main.aux 取正文编号，必须后编
    compile_one main
    compile_one appendix
    compile_one full
    ;;
  main)     compile_one main ;;
  appendix) compile_one appendix ;;
  full)     compile_one full ;;
  check)
    compile_one main
    compile_one appendix
    compile_one full
    ;;
  *) echo "未知参数：$1（可用：build / main / appendix / full / clean / check）"; exit 2 ;;
esac

echo
echo "编译完成。交付物："
report main.pdf     "正文（摘要 + 正文 + 参考文献；正文上限 30 页、不含源程序）"
report appendix.pdf "附录（A--S；页数不限，含全部源程序，需与正文一起装订）"
report full.pdf     "合并版（正文 + 附录，备用）"

if [ "${1:-build}" = "check" ]; then
  echo
  python3 tools/check_paper.py
fi
