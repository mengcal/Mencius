#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_version.py — 仓库元数据一致性自检（知夏 v1.3.2 复盘提案）

机械判据：agent_diary/__init__.py 的 __version__ 必须 == CHANGELOG.md 第一行
（`# AgentDiary vX.Y.Z`）里的版本号。两次复发（v1.1.0 串 v1.2.0、v1.3.0-mvp1
串 v1.3.2）证明这事不能靠自觉，必须机器拦。

用法：
    python scripts/check_version.py          # 在仓库根目录跑
退出码：0=一致；1=不一致或文件缺失。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "agent_diary", "__init__.py")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")


def die(msg):
    print("check_version: " + msg, file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.isfile(INIT):
        die("missing %s" % INIT)
    if not os.path.isfile(CHANGELOG):
        die("missing %s" % CHANGELOG)

    src = open(INIT, encoding="utf-8").read()
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', src, re.M)
    if not m:
        die("cannot find __version__ in %s" % INIT)
    py_ver = m.group(1).strip()

    head = open(CHANGELOG, encoding="utf-8").readline().strip()
    m2 = re.match(r"^#\s*AgentDiary\s+v?(\S+)", head)
    if not m2:
        die("CHANGELOG first line not like '# AgentDiary vX.Y.Z': %r" % head)
    cl_ver = m2.group(1).strip()

    # 容忍 v 前缀差异：py 侧 "1.3.2" vs changelog 侧 "v1.3.2"
    norm = lambda v: v.lstrip("vV")
    if norm(py_ver) != norm(cl_ver):
        die("MISMATCH: __version__=%r but CHANGELOG head=%r — 改版本号时两处必须一起改"
            % (py_ver, cl_ver))

    print("check_version: OK  __version__=%s == CHANGELOG head=%s" % (py_ver, cl_ver))


if __name__ == "__main__":
    main()
