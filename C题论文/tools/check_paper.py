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
PDF_APPENDIX = ROOT / "appendix.pdf"
PDF_FULL = ROOT / "full.pdf"
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
            + "。请由 code/plot/plot_figures.py（图 3--图 10）或 code/plot/plot_figures_v2.py"
            + "（图 11--图 15）生成后放入 figures/"
        )
    else:
        ok("插图：全部 \\includefig 引用的文件均已存在")


# ---------------------------------------------------------------------------
# 检查 6：源程序是否齐备（格式规范第五条 —— 取消评奖资格类红线）
#        双向核对：清单里的文件必须存在（正向），code/ 下的源程序必须全部入清单（反向）
# ---------------------------------------------------------------------------
CODE_DIR = ROOT / "code"
# 源程序口径：code/ 下（含子目录）的全部 .py 与 requirements.txt；
# 以 "_" 开头的是引导类辅助文件，同样必须入清单（它们也是参赛源程序的一部分）。
CODE_SUFFIXES = {".py", ".txt"}


def _listed_code(appendix_body: str) -> list[str]:
    return re.findall(r"\\codefile(?:\[[^\]]*\])?\{([^}]+)\}", appendix_body)


def _actual_code() -> list[str]:
    out = []
    for p in sorted(CODE_DIR.rglob("*")):
        if not p.is_file() or p.suffix not in CODE_SUFFIXES:
            continue
        if "__pycache__" in p.parts or p.name.startswith("."):
            continue
        out.append(p.relative_to(CODE_DIR).as_posix())
    return out


def check_code_files() -> None:
    apx = SECTIONS / "90_appendix.tex"
    if not apx.exists():
        return
    body = strip_comments(apx.read_text(encoding="utf-8"))
    names = _listed_code(body)

    missing = [n for n in names if not (CODE_DIR / n).exists()]
    if missing:
        err(
            "附录源程序缺失（格式规范第五条：缺少必要源程序可能被取消评奖资格）："
            + "、".join(missing)
            + "。请把全部可运行源程序放入 C题论文/code/（按每一问一类分目录：common/ q1/ q2/ q3/ q4/ exp/ plot/，"
            + "根目录放入口与工具），附录的 \\codefile 会自动原样引入；"
            + "目录与命名口径见 论文/README.md。"
        )

    unlisted = [n for n in _actual_code() if n not in names]
    if unlisted:
        err(
            "code/ 中存在未列入附录的源程序（格式规范第五条：论文未列全部源程序属红线）："
            + "、".join(unlisted)
            + "。请在 sections/90_appendix.tex 的附录 E 对应分节补 \\codefile{<相对 code/ 的路径>}"
            "（公共模块 common/、问题 1--4 各 q1/--q4/、对照实验 exp/、绘图 plot/、根目录直接写文件名）。"
        )

    if not missing and not unlisted:
        ok(
            f"附录源程序：清单 {len(names)} 项与 code/ 下实际源程序 {len(_actual_code())} 个双向一致"
            f"（{len(set(names))} 个唯一文件）"
        )

    check_run_all_coverage()


def check_run_all_coverage() -> None:
    """可复现性检查：四问、对照与绘图脚本必须都在 run_all.py 的计划内。

    common/ 下是公共模块（由脚本 import，不需单独运行），run_all/_pathsetup 自身是入口与引导。
    """
    runner = CODE_DIR / "run_all.py"
    if not runner.exists():
        return
    body = runner.read_text(encoding="utf-8")
    runnable = [
        n for n in _actual_code()
        if n.endswith(".py")
        and not n.startswith("common/")
        and n not in ("run_all.py", "_pathsetup.py")
    ]
    absent = [n for n in runnable if n not in body]
    if absent:
        err(
            "以下源程序不在 code/run_all.py 的复现计划内（一键复现会漏跑，论文数字将无法从零重建）："
            + "、".join(absent)
            + "。请把它们加入 STEPS（主链）/ FAST_EXTRA（信息结构与稳健性）/ "
            "V2_EXTRA（对照、消融与图件）/ FINAL（审计与台账）之一。"
        )
    else:
        ok(f"一键复现：run_all.py 覆盖全部 {len(runnable)} 个可运行脚本（四问、对照、绘图、审计与台账）")


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
                ok(f"正文共 {body_pages} 页（上限 30 页）；与附录合订时附录自第 {last_body + 1} 页起（当前为{mode}）")
        else:
            warn("未在 build/main.aux 中找到 pg:bodyend 标签，无法自动核算正文页数，请人工核对")
    else:
        warn("未找到 build/main.aux，无法自动核算正文页数；请用 --keep-intermediates 编译一次")

    if pages:
        print(f"\n  [参考] main.pdf 共 {pages} 页：摘要 1 页 + 正文 + 参考文献（附录另册，页数不限）")


# ---------------------------------------------------------------------------
# 检查 7b：三个交付物（main / appendix / full）齐备且都不含 ??
#   交付形态（用户指定）：
#     main.pdf      摘要页 + 正文 + 参考文献（正文 ≤30 页，不含任何源程序）
#     appendix.pdf  附录 A--O（独立文件，页数不限，含全部源程序，需与正文一起装订）
#     full.pdf      正文 + 附录合并版（备用）
#   附录里有 39 处回指正文的引用，靠 appendix.tex 里的 xr 读 build/main.aux 解析；
#   因此编译顺序必须是 main -> appendix。此检查同时守住"附录不能有 ?? 或标签名裸露"。
# ---------------------------------------------------------------------------
def check_deliverables() -> None:
    if not shutil_which("pdfinfo") or not shutil_which("pdftotext"):
        return
    for path, label, expect_appendix in [
        (PDF, "main.pdf（正文，≤30 页、不含源程序）", False),
        (PDF_APPENDIX, "appendix.pdf（附录，含全部源程序）", True),
        (PDF_FULL, "full.pdf（正文 + 附录合并版，备用）", True),
    ]:
        if not path.exists():
            warn(f"未生成 {path.name}（{label}），请运行 ./build.sh")
            continue
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
        m = re.search(r"Pages:\s+(\d+)", info)
        npages = int(m.group(1)) if m else 0
        size_mb = path.stat().st_size / 1024 / 1024
        txt = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
        bad = txt.count("??")
        head = txt.strip().split("\n")[0][:40] if txt.strip() else ""
        if bad:
            err(f"{path.name} 中有 {bad} 处「??」（未定义引用）")
        elif size_mb > 20:
            err(f"{path.name} 共 {size_mb:.1f} MB，超过 20 MB 上限")
        else:
            ok(f"{path.name}：{npages} 页、{size_mb:.1f} MB、无「??」（{label}）")
        # 正文那册不得出现源程序与附录标志（"正文不含代码"是格式规范的硬要求）
        # pdftotext 会在标题处断行，故比较前先去掉空白
        flat = re.sub(r"\s+", "", txt)
        if not expect_appendix:
            for marker in ("源程序：code/", "附录A", "支撑材料文件清单"):
                if marker.replace(" ", "") in flat:
                    err(f"{path.name} 中出现了「{marker}」，正文那册不得含附录/源程序")
        else:
            if "附录A支撑材料文件清单" not in flat:
                err(f"{path.name} 未检出附录起始（附录A 支撑材料文件清单），"
                    f"请确认已 \\input{{sections/90_appendix}}")


def shutil_which(cmd: str):
    from shutil import which

    return which(cmd)


# ---------------------------------------------------------------------------
# 检查 8：交叉引用完整性（本次新增）
#   事故背景：正文有一批 \ref 指向只在附录中定义的标签。此前 main.tex 不引入附录，
#   于是这些引用在 main.pdf 里全部渲染成「??」，而当时的 check_paper.py 没有任何
#   未定义引用检查（只查占位符/禁令词/身份/目录/插图/代码/PDF 结构），
#   所以 README 写着"未定义引用 0"却与实测不符。
#   三道防线：
#     ① 源码层：正文的每一个 \ref 目标都必须能在"正文 ∪ 附录"里找到；
#     ② 源码层：指向附录的引用必须用 \appref{label}{备用文字}，不得裸 \ref；
#     ③ 产物层：main.pdf 里出现「??」即失败。
# ---------------------------------------------------------------------------
def check_refs() -> None:
    body_files = [p for p in sorted(SECTIONS.glob("*.tex"))
                  if not p.name.startswith("90_")]
    app_files = sorted(SECTIONS.glob("90_*.tex"))

    def labels(paths) -> set[str]:
        found: set[str] = set()
        for p in paths:
            found |= set(re.findall(r"\\label\{([^}]+)\}", strip_comments(p.read_text(encoding="utf-8"))))
        return found

    body_labels = labels(body_files)
    app_labels = labels(app_files)

    # ① 正文里裸 \ref 的目标必须落在正文自身
    undefined = []
    for p in body_files:
        text = strip_comments(p.read_text(encoding="utf-8"))
        for m in re.finditer(r"\\ref\{([^}]+)\}", text):
            if m.group(1) not in body_labels:
                line = text[:m.start()].count("\n") + 1
                undefined.append(f"{p.name}:{line} \\ref{{{m.group(1)}}}")
    if undefined:
        err("正文存在未定义引用（会渲染成 ??，必须修）：\n      " + "\n      ".join(undefined))
    else:
        ok(f"交叉引用：正文 {len(body_labels)} 个标签、全部 \\ref 目标均可解析")

    # ② 指向附录的引用必须走 \appref
    bare_app = []
    for p in body_files:
        text = strip_comments(p.read_text(encoding="utf-8"))
        for m in re.finditer(r"\\ref\{([^}]+)\}", text):
            if m.group(1) in app_labels:
                line = text[:m.start()].count("\n") + 1
                bare_app.append(f"{p.name}:{line} \\ref{{{m.group(1)}}}")
    if bare_app:
        err(
            "以下引用指向附录标签却用了裸 \\ref（appendix 未载入时会变成 ??）：\n      "
            + "\n      ".join(bare_app)
            + "\n      请改为 \\appref{label}{备用文字}"
        )
    else:
        ok("交叉引用：指向附录的引用全部使用 \\appref（无裸 \\ref 跨入附录）")

    # ③ 产物层：三册 PDF 中均不得出现 ??
    if shutil_which("pdftotext"):
        for path in (PDF, PDF_APPENDIX, PDF_FULL):
            if not path.exists():
                continue
            txt = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
            n = txt.count("??")
            if n:
                err(f"{path.name} 中有 {n} 处「??」（未定义引用），必须修复后重新编译")
            else:
                ok(f"交叉引用：{path.name} 全文无「??」")


# ---------------------------------------------------------------------------
# 检查 9bis：附录定位核对（本次新增）
#   背景：\appref 的第二个参数是**手写**的附录定位（实际字母/小节号 + 名称），
#   它一旦与实际附录编号漂移，正文就会指向一个不存在的附录（"跳号附录"缺陷：
#   正文引用 E/F/H/I/J，而附录实际是 A--S，A--D 与 G 从不被引用）。
#   本检查从 sections/90_*.tex 的 \section / \subsection 顺序重建"标签 → 附录定位"，
#   再逐条比对正文 \appref 的第二个参数前缀，任何不一致即失败。
# ---------------------------------------------------------------------------
def check_appendix_locators() -> None:
    app_files = sorted(SECTIONS.glob("90_*.tex"))
    if not app_files:
        warn("附录定位核对：未找到 90_*.tex，跳过")
        return
    loc: dict[str, str] = {}
    for path in app_files:
        sec = 0
        sub = 0
        for line in strip_comments(path.read_text(encoding="utf-8")).splitlines():
            if re.match(r"\s*\\section\{", line):
                sec += 1
                sub = 0
            elif re.match(r"\s*\\subsection\{", line):
                sub += 1
            for m in re.finditer(r"\\label\{([^}]+)\}", line):
                letter = chr(ord("A") + sec - 1) if sec else "?"
                loc[m.group(1)] = f"{letter}.{sub}" if sub else letter

    body_files = [p for p in sorted(SECTIONS.glob("*.tex")) if not p.name.startswith("90_")]
    bad: list[str] = []
    checked = 0
    for p in body_files:
        text = strip_comments(p.read_text(encoding="utf-8"))
        for m in re.finditer(r"\\appref\{([^}]+)\}\{([^}]*)\}", text):
            label, textarg = m.group(1), m.group(2)
            line = text[: m.start()].count("\n") + 1
            checked += 1
            if label not in loc:
                bad.append(f"{p.name}:{line} \\appref{{{label}}} 的标签在附录中不存在")
                continue
            claim = re.match(r"\s*([A-Z](?:\.\d+)?)\b", textarg)
            if not claim:
                bad.append(f"{p.name}:{line} \\appref{{{label}}} 的定位文字不以附录字母开头：{textarg!r}")
                continue
            if claim.group(1) != loc[label]:
                bad.append(
                    f"{p.name}:{line} \\appref{{{label}}} 写为「{claim.group(1)} …」，"
                    f"实际应为「{loc[label]} …」"
                )
    if bad:
        err("附录定位不一致（\appref 第二参数必须等于实际附录字母/小节号）：\n      " + "\n      ".join(bad))
    else:
        ok(f"附录定位：正文 {checked} 处 \\appref 与实际附录编号（A--S）逐条一致")


# ---------------------------------------------------------------------------
# 检查 9：行文风格（本次新增，只报"可机械判定"的项，全部为 WARNING）
#   依据：论文写作规范——术语唯一、句长可控、标点体例统一。
# ---------------------------------------------------------------------------
STYLE_TERMS = [
    # (禁用写法, 统一写法, 说明)
    ("完美信息", "完全信息", "同一概念两种名称（perfect information）"),
    ("口径口径", "口径", "模板句叠加产生的重复词"),
]

def check_style() -> None:
    tex_files = tex_sources()
    hits = []
    for bad, good, why in STYLE_TERMS:
        for p in tex_files:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("%"):
                    continue
                if bad in line:
                    hits.append(f"{p.name}:{i} 「{bad}」→ 统一为「{good}」（{why}）")
    if hits:
        warn("术语/体例不统一：\n      " + "\n      ".join(hits))
    else:
        ok("行文风格：术语与体例关键项统一（无「完美信息」「口径口径」等混用）")

    # 硬编码章号：正文不得写「第X章」，一律用 \chapref
    hard = []
    for p in [q for q in tex_files
              if q.parent.name == "sections" and not q.name.startswith("90_")
              and q.name != "refs.tex"]:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            if re.search(r"第[一二三四五六七八九十]+章", line) or "§" in line:
                hard.append(f"{p.name}:{i}")
    if hard:
        warn(
            "硬编码章节号（改章序会失配，建议改用 \\chapref / \\ref）：\n      "
            + "、".join(hard)
        )
    else:
        ok("行文风格：正文无硬编码章号，全部走 \\chapref / \\ref")

    # 表注体例：只允许「表注：」一种
    badcap = []
    for p in [q for q in tex_files if q.parent.name == "sections"]:
        text = strip_comments(p.read_text(encoding="utf-8"))
        for m in re.finditer(r"\{\\footnotesize\s*注[：:]", text):
            badcap.append(p.name)
    if badcap:
        warn("表注体例不统一（应统一为「表注：」）：" + "、".join(sorted(set(badcap))))
    else:
        ok("行文风格：表注体例统一为「表注：」")

    # 英文直引号：正文不得出现（中文引号用 “ ”）
    straight = []
    for p in [q for q in tex_files if q.parent.name == "sections"]:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            if '"' in line:
                straight.append(f"{p.name}:{i}")
    if straight:
        warn("存在英文直引号（应改为中文引号 “ ”）：\n      " + "、".join(straight))
    else:
        ok("行文风格：引号统一为中文弯引号")

    # 超长句：正文散文句 >150 字给出提示（表内长行不计）
    long_sent = []
    for p in [q for q in tex_files
              if q.parent.name == "sections" and not q.name.startswith("90_")
              and q.name != "refs.tex"]:
        text = strip_comments(p.read_text(encoding="utf-8"))
        text = re.sub(r"\\begin\{(table|figure|tabularx|tabular|equation|align|algorithm)\}.*?"
                      r"\\end\{\1\}", "", text, flags=re.S)
        text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", "", text)
        text = re.sub(r"\\\(.*?\\\)", "", text, flags=re.S)
        text = re.sub(r"[{}\\]", "", text).replace("\n", "")
        for s in re.split(r"[。；！？]", text):
            s = s.strip()
            if len(s) >= 150:
                long_sent.append(f"{p.name}（{len(s)} 字）：{s[:40]}…")
    if long_sent:
        warn(f"超长句 {len(long_sent)} 处（≥150 字，建议一句一个判断）：\n      "
             + "\n      ".join(long_sent[:8]))
    else:
        ok("行文风格：正文无 ≥150 字的散文长句")


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
    check_deliverables()
    check_refs()
    check_appendix_locators()
    check_style()

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
