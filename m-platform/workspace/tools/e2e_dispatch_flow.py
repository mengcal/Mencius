# -*- coding: utf-8 -*-
"""e2e_dispatch_flow.py — 派活→部门→汇报环唤醒 端到端流程脚本（09-15 盲区补测一期）。

⚠ 适用环境定位（09-16 fix4，爸爸批 b 路）：**本件仅适用本地裸跑环境**。
guard 化部署下 settings_mgr.get_api_token() 恒空=按设计拒跑（09-16 结构性互斥定案，
不是 bug、不是待修）——活体验证走米娅 UI 真派单 + 主会话核账，**勿再试图绕 token**。

⚠ 本件只写不跑活体（工单钉）：真实执行由 test-runner 后续挂上——
模型面钉死 书生/佰全/0423 的 glm-4.5-air（上下文小，任务文本机械限 ≤200 字），
脚本头部硬断言 model/provider 名不含 modelscope/魔搭（含=直接拒跑，不发消息——
魔搭是中文渠道名，光钉 ASCII 串拦不住，09-15 E2E 拒跑案附带发现）。

流程（对齐 dept_watch v2 实态）：
1. settings_mgr.get_api_token() 取管理员 token（唯一真源 .settings_secrets，
   guard 模式返回空=fail-closed 拒跑；全程零硬编码密钥）。
2. langgraph_sdk get_sync_client(url=默认 http://127.0.0.1:2024) 新建线程。
3. runs.create("agent", input={"messages":[微任务], "mia_config":{"model":…}}) ——
   微任务=强制 start_async_task 派部门 + 自带"完成标志:"行（dept_watch register 提取面）。
4. 轮询主线程 get_state 等【部门自动汇报】唤醒（默认 5min 超时）。
5. 断言完成标志机械核对附注两分支之一可判：
   - 附注出现（miss 分支）→ 必含"未在部门末条汇报中命中"+ check_async_task 指引；
   - 附注缺席（hit 分支）→ 唤醒文本含标志词，视为全命中（dept_watch 语义：全命中=不附注）。
退出码：0=唤醒且分支判定通过；2=超时未唤醒；3=前置校验失败（token/模型名/文本超限）。

宿主手跑 --help 即可看参数；主流程必须带活体服务器，本仓测试件（tools/test_dept_watch.py）
已在 mock 面覆盖同一判定逻辑，此处仅是活体链路验收件。
"""
import argparse
import sys
import time

DEFAULT_URL = "http://127.0.0.1:2024"
DEFAULT_MODEL = "glm-4.5-air"          # 0423 书生/佰全渠道的主力小名（上下文小）
BANNED_PROVIDER_SUBSTRS = ("modelscope", "魔搭")  # 硬断言：任何渠道名/模型名含这些串=直接拒跑
# 09-15 E2E 拒跑案附带发现：settings 里渠道中文名就叫"魔搭1/2/3号"，只钉 ASCII 串
# "modelscope" 拦不住中文名——blob 已 .lower()，中文不受 lowercase 影响，同形可比。
WAKE_MARK = "【部门自动汇报】"
NOTE_MARK = "【完成标志机械核对】"
FLAG_TEXT = "已读工作规范首行"           # 完成标志全文，机械核对两分支共用

# 微任务：≤200 字硬限 + 强制派部门 + 自带"完成标志:"行（r56 缺口①登记面）
TASK = (
    "演习微任务（不改任何文件，不外发）：用 start_async_task 把下面这句原样派给任一部门："
    "『读 mia_home/notes/工作规范.md 的第一行并原样回报。完成标志: 已读工作规范首行』。"
    "派完不等结果，等【部门自动汇报】唤醒后用 check_async_task 取汇报转呈。"
)


def _preflight(args):
    """前置硬断言：全在触网之前做完，任一失败 exit 3。"""
    blob = f"{args.model}|{args.provider or ''}".lower()
    _hit = [b for b in BANNED_PROVIDER_SUBSTRS if b in blob]
    if _hit:
        print(f"[e2e] ✗ 拒跑：模型/服务商名含 {_hit}（{blob}）")
        sys.exit(3)
    if len(TASK) > 200:
        print(f"[e2e] ✗ 任务文本 {len(TASK)} 字超 200 上限（glm-4.5-air 上下文小）")
        sys.exit(3)
    print(f"[e2e] 前置通过：任务 {len(TASK)} 字，model={args.model} provider={args.provider or '-'}")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from settings_mgr import get_api_token
    token = get_api_token()
    if not token:
        print("[e2e] ✗ 无管理员 token（settings_mgr.get_api_token 空=guard 模式或未配置）。"
              "X-Internal-Key 只活在服务器进程内存，跨进程不可得——fail-closed 拒跑。")
        sys.exit(3)
    return token


def _fetch_client(args, token):
    from langgraph_sdk import get_sync_client
    return get_sync_client(url=args.url, headers={"Authorization": f"Bearer {token}"})


def _wake_payloads(state):
    """从主线程 state 提取含唤醒标记的消息文本列表。"""
    msgs = (state.get("values") or {}).get("messages") or []
    out = []
    for m in msgs:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if content and WAKE_MARK in str(content):
            out.append(str(content))
    return out


def main():
    ap = argparse.ArgumentParser(
        prog="e2e_dispatch_flow",
        description="派活→部门→dept_watch 汇报环唤醒 E2E（活体件；--help 不触网）")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"langgraph server（默认 {DEFAULT_URL}）")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="覆盖 mia_config.model（默认 glm-4.5-air；含 modelscope/魔搭 直接拒跑）")
    ap.add_argument("--provider", default=None,
                    help="可选服务商名（同样受 modelscope/魔搭 硬断言约束）")
    ap.add_argument("--assistant", default="agent", help="主图 assistant_id（默认 agent）")
    ap.add_argument("--timeout", type=int, default=300, help="等唤醒超时秒（默认 300=5min）")
    ap.add_argument("--poll", type=int, default=5, help="轮询间隔秒（默认 5）")
    args = ap.parse_args()

    token = _preflight(args)
    client = _fetch_client(args, token)

    th = client.threads.create()
    tid = th["thread_id"] if isinstance(th, dict) else th.thread_id
    print(f"[e2e] 新主线程 {tid}")

    mia_config = {"model": args.model}
    if args.provider:
        mia_config["provider"] = args.provider
    client.runs.create(
        tid, args.assistant,
        input={"messages": [{"role": "user", "content": TASK}], "mia_config": mia_config},
        config={"configurable": {"user_id": "e2e-dispatch-flow"}},
    )
    print(f"[e2e] 微任务已发出，轮询等 {WAKE_MARK}（≤{args.timeout}s）…")

    deadline = time.time() + args.timeout
    wakes = []
    while time.time() < deadline:
        time.sleep(args.poll)
        try:
            state = client.threads.get_state(tid)
        except Exception as e:
            print(f"[e2e]   get_state 瞬断（继续等）：{e}")
            continue
        wakes = _wake_payloads(state)
        if wakes:
            break
        print("[e2e]   …未唤醒")

    if not wakes:
        print(f"[e2e] ✗ 超时 {args.timeout}s 未见 {WAKE_MARK}——汇报环断链，主线程尾部："
              f"\n{str(client.threads.get_state(tid))[-600:]}")
        sys.exit(2)

    wake = wakes[-1]
    print(f"[e2e] 唤醒到达（{len(wakes)} 次），判定机械核对附注分支：")
    if NOTE_MARK in wake:
        # miss 分支：附注出现 → 必带未命中明细与取全文指引（钉 dept_watch r56 语义）
        import re
        checks = {
            "含未命中字样": "条标志未在部门末条汇报中命中" in wake,
            "计数形态 n/m": bool(re.search(r"\d+/\d+ 条标志未在", wake)),
            "含取全文指引": "check_async_task" in wake,
            "含标志原文": FLAG_TEXT in wake,
        }
        print(f"[e2e]   分支=标志未命中(miss)：{checks}")
        bad = [k for k, v in checks.items() if not v]
        print(f"[e2e] {'✗ miss 分支断言失败: ' + str(bad) if bad else '✓ miss 分支判定通过'}")
        sys.exit(1 if bad else 0)
    # hit 分支：无附注 = 全部标志命中（附注缺席即命中态，wake 内嵌标志词佐证）
    hit_ok = FLAG_TEXT in wake
    print(f"[e2e]   分支=标志全命中(hit)（无附注），标志词随派活文本在唤醒消息={hit_ok}")
    print("[e2e] ✓ hit 分支判定通过" if hit_ok
          else "[e2e] ✗ hit 分支存疑：无附注但唤醒文本未见标志词，请人工核对 desc 截断")
    sys.exit(0 if hit_ok else 1)


if __name__ == "__main__":
    main()
