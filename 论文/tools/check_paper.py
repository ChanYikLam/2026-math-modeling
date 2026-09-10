#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_paper.py —— 2026 CUMCM C 题论文提交前合规自查
================================================================================
把《全国大学生数学建模竞赛论文格式规范（2026 年修订稿）》与写作需求文档中
**可机械执行**的条款做成脚本检查，避免"人眼漏看"。

用法：
    python3 tools/check_paper.py            # 检查源码 + 已生成的 main.pdf
    python3 tools/check_paper.py --strict   # 有占位符也算失败（定稿模式必用）

退出码：0 = 无 ERROR；1 = 存在 ERROR；2 = 脚本自身出错。

说明：本脚本只做**机械可判**的检查（红线类与字面类）。
      "模型是否正确""结论是否有证据" 一类判断必须由人完成（见论文 §14 总检清单）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ROOT / "sections"
PDF = ROOT / "main.pdf"
AUX = ROOT / "build" / "main.aux"

ERRORS: list[str] = []
WARNINGS: list[str] = []
PASSED: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def warn(msg: str) -> None:
    WARNINGS.append(msg)


def ok(msg: str) -> None:
    PASSED.append(msg)


def tex_sources() -> list[Path]:
    files = [ROOT / "main.tex", ROOT / "preamble.tex"]
    files += sorted(SECTIONS.glob("*.tex"))
    files += sorted((ROOT / "figures").glob("*.tex"))
    return [f for f in files if f.exists()]


def strip_comments(text: str) -> str:
    """去掉 LaTeX 注释行（% 之后），避免把写作提示里的示例词当成正文。"""
    out = []
    for line in text.splitlines():
        # 未转义的 % 视为注释起点
        m = re.search(r"(?<!\\)%", line)
        out.append(line[: m.start()] if m else line)
    return "\n".join(out)


def strip_guideblocks(text: str) -> str:
    """去掉【写作提示】块。

    guideblock 里写的是"不要这样写"的反例与写作纪律，
    不应被禁令词表、身份信息表当成正文违规。
    """
    return re.sub(r"\\begin\{guideblock\}.*?\\end\{guideblock\}", "", text, flags=re.S)


def readable_source(f: Path) -> str:
    """正文可读文本 = 去掉注释与写作提示块。"""
    return strip_guideblocks(strip_comments(f.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# 检查 1：占位符（D1 数字纪律 / §14 A5）
# ---------------------------------------------------------------------------
def check_placeholders(strict: bool) -> None:
    total = 0
    hits = []
    for f in tex_sources():
        if f.name == "preamble.tex":
            continue  # 宏定义本身不算
        body = readable_source(f)
        n = len(re.findall(r"\\ph(\[[^\]]*\])?", body))
        if n:
            hits.append((f.relative_to(ROOT), n))
            total += n
    if total == 0:
        ok("占位符：全文无 {待计算} 占位符")
    else:
        detail = "，".join(f"{p}({n})" for p, n in hits)
        msg = (
            f"占位符：仍有 {total} 处 {{{{待计算}}}} 占位符 —— {detail}。"
            "D1 数字纪律要求：论文中每个数值都必须由本队代码从原始附件算出；未算出时保留占位符，"
            "严禁编造。定稿前必须全部替换。"
        )
        (err if strict else warn)(msg)


# ---------------------------------------------------------------------------
# 检查 2：禁令词表（§10.3）
# ---------------------------------------------------------------------------
BANNED_HARD = {
    "效果良好": "空话，改为具体残差/区间",
    "精度较高": "空话，改为具体 MAE/RMSE 与样本量",
    "数据有限": "空话，改为具体数据需求与影响方向",
    "模型有待改进": "空话，改为局限四要素",
    "随着我国经济快速发展": "无信息量套话，删除",
    "能源互联网蓬勃发展": "无信息量套话，删除",
    "首次": "过度声称，改为「在本题参数范围内」",
    "显著领先": "过度声称，改为「相对基线改善 x%」",
    "普遍适用": "过度声称，改为限定适用范围",
    "数字孪生": "与本题模型无关的包装，删除",
    "元宇宙": "与本题模型无关的包装，删除",
    "区块链": "与本题模型无关的包装，删除",
}

BANNED_CONTEXT = {
    "导致": "因果误述：电价—负载/光伏关系只能写「共动」「同向变动」",
    "引起": "因果误述：同上",
    "造成": "因果误述：同上",
    "由此可得": "无证据结论：需补证据 ID 与图表式引用",
    "结果表明": "无证据结论：需补证据 ID 与图表式引用",
}


def check_banned_words() -> None:
    hard, ctx = [], []
    for f in tex_sources():
        body = readable_source(f)
        for i, line in enumerate(body.splitlines(), 1):
            for w, why in BANNED_HARD.items():
                if w in line:
                    hard.append(f"{f.relative_to(ROOT)}:{i}: 「{w}」 —— {why}")
            for w, why in BANNED_CONTEXT.items():
                if w in line:
                    ctx.append(f"{f.relative_to(ROOT)}:{i}: 「{w}」 —— {why}")
    if hard:
        err("禁令词（必须修改）：\n      " + "\n      ".join(hard))
    else:
        ok("禁令词：未出现硬性禁止的空话/过度声称")
    if ctx:
        warn("需人工确认的措辞（可能误报，逐条核对上下文）：\n      " + "\n      ".join(ctx))
    else:
        ok("措辞：未出现因果误述与无证据结论的典型措辞")


# ---------------------------------------------------------------------------
# 检查 3：身份信息（格式规范第六条、第十一条 —— 取消评奖资格类红线）
# ---------------------------------------------------------------------------
IDENTITY_PATTERNS = [
    (r"(?<![国生])[\u4e00-\u9fa5]{2}大学", "疑似学校名"),
    (r"[\u4e00-\u9fa5]{2}学院", "疑似学院名"),
    (r"指导教师", "指导教师信息"),
    (r"参赛队号|报名队号|队号", "参赛队号"),
    (r"赛区", "赛区信息"),
    (r"承诺书", "承诺书内容（电子版不得出现）"),
    (r"编号专用页", "编号专用页（电子版不得出现）"),
    (r"\b\d{12}\b", "疑似 12 位队号"),
]


def check_identity() -> None:
    hits = []
    for f in tex_sources():
        body = readable_source(f)
        for i, line in enumerate(body.splitlines(), 1):
            for pat, why in IDENTITY_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}: {why} —— {line.strip()[:50]}")
    if hits:
        err("身份信息（取消评奖资格类红线，必须清除）：\n      " + "\n      ".join(hits))
    else:
        ok("身份信息：全文未检出学校、队号、姓名、赛区信息")
    # PDF 元数据
    if PDF.exists() and shutil_which("pdfinfo"):
        out = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
        for key in ("Author", "Creator"):
            m = re.search(rf"^{key}:\s*(.*)$", out, re.M)
            if m and m.group(1).strip() not in ("", "xdvipdfmx", "tectonic", "LaTeX with hyperref"):
                warn(f"PDF 元数据 {key} 非空：「{m.group(1).strip()}」，请确认不含身份信息")


# ---------------------------------------------------------------------------
# 检查 4：目录与结构（格式规范第四条：不要目录）
# ---------------------------------------------------------------------------
def check_no_toc() -> None:
    hits = [f.name for f in tex_sources() if r"\tableofcontents" in strip_comments(f.read_text(encoding="utf-8"))]
    if hits:
        err(f"格式规范第四条明确「不要目录」，但以下文件出现 \\tableofcontents：{hits}")
    else:
        ok("目录：全文未使用 \\tableofcontents（符合第四条）")


# ---------------------------------------------------------------------------
# 检查 5：图片文件是否齐备
# ---------------------------------------------------------------------------
def check_figures() -> None:
    missing = []
    for f in [ROOT / "main.tex"] + sorted(SECTIONS.glob("*.tex")):
        body = strip_comments(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"\\includefig(?:\[[^\]]*\])?\{([^}]+)\}", body):
            name = m.group(1)
            if not (ROOT / "figures" / name).exists():
                missing.append(name)
    if missing:
        warn(
            "缺图（编译时会显示红框占位，不影响编译）："
            + "、".join(sorted(set(missing)))
            + "。请由 scripts/plot_*.py 生成后放入 figures/"
        )
    else:
        ok("插图：全部 \\includefig 引用的文件均已存在")


# ---------------------------------------------------------------------------
# 检查 6：源程序是否齐备（格式规范第五条 —— 取消评奖资格类红线）
# ---------------------------------------------------------------------------
def check_code_files() -> None:
    apx = SECTIONS / "90_appendix.tex"
    if not apx.exists():
        return
    body = strip_comments(apx.read_text(encoding="utf-8"))
    names = re.findall(r"\\codefile(?:\[[^\]]*\])?\{([^}]+)\}", body)
    missing = [n for n in names if not (ROOT / "code" / n).exists()]
    if missing:
        err(
            "附录源程序缺失（格式规范第五条：缺少必要源程序可能被取消评奖资格）："
            + "、".join(missing)
            + "。请把全部可运行源程序放入 code/ 目录，附录会自动原样引入。"
        )
    else:
        ok(f"附录源程序：{len(names)} 个文件齐备（{len(set(names))} 个唯一文件）")


# ---------------------------------------------------------------------------
# 检查 7：PDF 结构（页数、摘要页、正文页数上限）
# ---------------------------------------------------------------------------
def check_pdf(strict: bool) -> None:
    if not PDF.exists():
        warn("尚未生成 main.pdf，跳过 PDF 结构检查（先运行 ./build.sh）")
        return
    if not shutil_which("pdfinfo") or not shutil_which("pdftotext"):
        warn("未找到 pdfinfo / pdftotext（poppler），跳过 PDF 结构检查")
        return

    info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", info)
    pages = int(m.group(1)) if m else None
    size_mb = PDF.stat().st_size / 1024 / 1024
    if size_mb > 20:
        err(f"电子版文件大小 {size_mb:.1f} MB 超过 20 MB 上限（格式规范第十条）")
    else:
        ok(f"电子版大小：{size_mb:.1f} MB（上限 20 MB）")

    def page_text(p: int) -> str:
        return subprocess.run(
            ["pdftotext", "-f", str(p), "-l", str(p), str(PDF), "-"],
            capture_output=True, text=True,
        ).stdout

    # 第一页必须是摘要页（电子版不放承诺书与编号页）
    p1 = page_text(1)
    if "储能调度；线性规划" in p1 or "关键词" in p1:
        ok("电子版第 1 页为摘要页（含关键词），符合第十条")
    else:
        err(
            "电子版第 1 页未检出摘要页标志（关键词）。"
            "格式规范第十条要求：电子版第一页必须为摘要专用页，不得含承诺书与编号专用页。"
        )
    if "随着光伏等分布式电源" in p1:
        err("第 1 页已出现正文内容，说明摘要超过一页（格式规范第三条）")
    elif "随着光伏等分布式电源" in page_text(2):
        ok("摘要页恰为 1 页，正文自第 2 页开始")

    # 正文页数：用 aux 中的 pg:bodyend 标签定位正文末页
    if AUX.exists():
        aux = AUX.read_text(encoding="utf-8", errors="ignore")
        lm = re.search(r"\\newlabel\{pg:bodyend\}\{\{([^}]*)\}\{(\d+)\}", aux)
        if lm:
            last_body = int(lm.group(2))
            body_pages = last_body - 1
            final_mode = (ROOT / "final.flag").exists()
            if body_pages > 30:
                msg = (
                    f"正文 {body_pages} 页，超过 30 页上限"
                    f"（格式规范第四条，第 {last_body} 页为正文末页）"
                )
                if final_mode:
                    err(msg)
                else:
                    warn(
                        msg + "。当前为**写作期（草稿）模式**，页数含【写作提示】块，"
                        "并不等于定稿页数；定稿前请执行 touch final.flag 后重新编译并检查。"
                    )
            else:
                mode = "定稿模式" if final_mode else "写作期（草稿）模式"
                ok(f"正文共 {body_pages} 页（上限 30 页），附录自第 {last_body + 1} 页起（当前为{mode}）")
        else:
            warn("未在 build/main.aux 中找到 pg:bodyend 标签，无法自动核算正文页数，请人工核对")
    else:
        warn("未找到 build/main.aux，无法自动核算正文页数；请用 --keep-intermediates 编译一次")

    if pages:
        print(f"\n  [参考] PDF 总页数 {pages}：摘要 1 页 + 正文 + 参考文献 + 附录（附录页数不限）")


def shutil_which(cmd: str):
    from shutil import which

    return which(cmd)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="CUMCM 论文提交前合规自查")
    ap.add_argument("--strict", action="store_true", help="把占位符也视为错误（定稿模式）")
    args = ap.parse_args()

    print("=" * 78)
    print("  CUMCM 2026 C 题论文 —— 提交前合规自查")
    print("=" * 78)

    check_placeholders(args.strict)
    check_banned_words()
    check_identity()
    check_no_toc()
    check_figures()
    check_code_files()
    check_pdf(args.strict)

    print("\n" + "-" * 78)
    for m in PASSED:
        print(f"  [通过] {m}")
    for m in WARNINGS:
        print(f"  [注意] {m}")
    for m in ERRORS:
        print(f"  [失败] {m}")
    print("-" * 78)

    if ERRORS:
        print(f"\n结论：存在 {len(ERRORS)} 项必须处理的失败项（另有 {len(WARNINGS)} 项注意）。")
        print("      A 组红线（身份信息、附录源码、正文页数、摘要页）任一不过，都不要提交。")
        return 1
    print(f"\n结论：全部机械检查通过（{len(WARNINGS)} 项注意需人工确认）。")
    print("      仍需人工完成：证据账本完整性、每张图注的四要素、参考文献逐条核对。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
