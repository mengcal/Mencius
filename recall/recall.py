#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recall.py — WeChat-style on-demand recall for AI agents.

零依赖（仅 Python 标准库）。多关键词 = 同一行 AND（微信搜聊天记录的手感），
结果按日期分组、倒序、带 `出处:行号`，供智能体在自己的上下文里直接引用。

用法:
    python recall.py 关键词 [关键词2 ...] [--days N] [--sources FILE] [--max-hits N]

数据源配置（按顺序找第一个存在的）:
    1) --sources 指定的文件
    2) 环境变量 RECALL_SOURCES（单个文件路径）
    3) 当前目录 ./recall-sources.txt
    4) 用户目录 ~/.recall-sources.txt

配置格式（每行一条，# 注释；UTF-8/GBK/BOM 均可读）:
    标签=路径或glob        例:  对话全量=exports/conversations.md
    路径或glob             例:  logs/eng-log.md        （标签=文件名）
    例:  日记=notes/diary/*.md

设计口径:
    - 搜的是"你导出/落盘的纯文本档案"，不解析任何厂商私有格式——所以它对
      Claude Code / Codex / ZCode / Qoder / CodeBuddy 的导出物一视同仁。
    - 日期优先级：行内显式 `YYYY-MM-DD` > 标题行继承 > 文件名日期 > 文件 mtime。
    - 关键词匹配大小写不敏感。
    - 永不递归进二进制/图片目录：由配置者自律（只列文本路径），脚本本身不猜。
"""
import sys, os, re, glob, datetime

def warn(msg):
    print("recall: " + msg, file=sys.stderr)

def load_sources(cli_path=None):
    cand = []
    if cli_path:
        cand.append(cli_path)
    env = os.environ.get("RECALL_SOURCES")
    if env:
        cand.append(env)
    cand.append(os.path.join(os.getcwd(), "recall-sources.txt"))
    cand.append(os.path.join(os.path.expanduser("~"), ".recall-sources.txt"))
    for p in cand:
        if p and os.path.isfile(p):
            raw = open(p, "rb").read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")   # Windows 记事本 ANSI 兜底
            out = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    label, path = line.split("=", 1)
                else:
                    label, path = "", line
                label, path = label.strip(), path.strip()
                files = sorted(glob.glob(os.path.expanduser(path)))
                if not files:
                    warn("config line matched nothing: %s" % line)
                    continue
                for f in files:
                    out.append((label or os.path.basename(f), f))
            return out, p
    return [], None

DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")

def file_fallback_date(path):
    m = DATE_RE.search(os.path.basename(path).replace("/", "-"))
    if m:
        return m.group(1)
    try:
        return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    except Exception:
        return "0000-00-00"

def die(msg):
    print("recall: " + msg, file=sys.stderr)
    sys.exit(2)

def parse_int(name, argv, i):
    if i + 1 >= len(argv):
        die("%s requires a value" % name)
    try:
        return int(argv[i + 1]), i + 2
    except ValueError:
        die("%s expects an integer, got %r" % (name, argv[i + 1]))

def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    kw, days, sources_file, max_hits = [], None, None, 200
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--days":
            days, i = parse_int("--days", argv, i); continue
        if a == "--max-hits":
            max_hits, i = parse_int("--max-hits", argv, i); continue
        if a == "--sources":
            if i + 1 >= len(argv):
                die("--sources requires a file path")
            sources_file = argv[i + 1]; i += 2; continue
        if a.startswith("--"):
            die("unknown option: %s" % a)
        kw.append(a); i += 1
    if not kw:
        die("give me at least one keyword")
    if days is not None and days < 0:
        die("--days must be >= 0")

    sources, used_cfg = load_sources(sources_file)
    if not sources:
        if used_cfg:
            die("config %s exists but matched no readable files" % used_cfg)
        die("no sources configured — see recall-sources.txt format in --help")
    pats = [re.compile(re.escape(k), re.I) for k in kw]
    cutoff = None
    if days is not None:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    hits = []
    for tag, path in sources:
        try:
            lines = open(path, encoding="utf-8", errors="replace").readlines()
        except Exception as e:
            warn("skip unreadable %s (%s)" % (path, e))
            continue
        fbase = file_fallback_date(path)
        cur = ""
        rel = os.path.relpath(path)
        fname = os.path.basename(path)
        for n, line in enumerate(lines, 1):
            s = line.rstrip()
            body = s.strip("#>- ")
            if DATE_RE.fullmatch(body) or re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d(:\d\d)?$", body):
                cur = body[:10]                  # 纯日期/日期时间行=标题，继承之
                date = cur
            else:
                im = DATE_RE.search(s)              # 行内显式日期优先
                date = im.group(1) if im else (cur or fbase)
            if cutoff and date < cutoff:
                continue
            if all(p.search(s) for p in pats):
                hits.append((date, tag, "%s:%d" % (rel, n), s[:300]))
    hits.sort(key=lambda h: h[0], reverse=True)
    print("# recall: %s   (%d hits, sources=%s)" % (" AND ".join(kw), len(hits), used_cfg or "-"))
    last = None
    for date, tag, where, text in hits[:max_hits]:
        if date != last:
            print("\n## " + date); last = date
        print("- [%s] %s\n  %s" % (tag, where, text))
    if len(hits) > max_hits:
        print("\n... %d more (raise --max-hits)" % (len(hits) - max_hits))

if __name__ == "__main__":
    main()
