# -*- coding: utf-8 -*-
"""源程序子目录引导：唯一一处 sys.path 设置，供全部脚本复用。
=============================================================
本工程按“每一问一类”组织源程序，脚本之间的调用关系保持扁平：

    code/
    +-- _pathsetup.py        本文件（子目录引导）
    +-- run_all.py           一键复现入口
    +-- audit.py             独立审计 AU1--AU10
    +-- paper_numbers.py     数值台账汇总
    +-- requirements.txt     依赖清单
    +-- common/             口径与公共建模模块（config/lp_engine/results_io/copula/scen_copula）
    +-- q1/ q2/ q3/ q4/     四问的求解脚本
    +-- exp/                横向对照实验与验证脚本
    +-- plot/               绘图脚本

用法（必须放在 ``from __future__ import annotations`` **之后**，因为未来导入必须是
文档字符串之外的第一个语句）：

    # 子目录脚本（common/ q1/ q2/ q3/ q4/ exp/ plot/）
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import _pathsetup                     # 把 common/ 与各问目录加入 sys.path

    # 位于 code/ 根目录的脚本（run_all/audit/paper_numbers）
    import _pathsetup

引入本模块后，``import config`` / ``import lp_engine`` / ``import q3`` 等扁平导入
在任意工作目录下都能解析，因此既可以 ``python3 code/run_all.py`` 一键复现，
也可以单独运行 ``python3 code/exp/exp_dro.py``。
"""
from __future__ import annotations

import os
import sys

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBDIRS = ("common", "q1", "q2", "q3", "q4", "exp", "plot")

for _name in SUBDIRS:
    _path = os.path.join(CODE_DIR, _name)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
