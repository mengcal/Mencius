"""M平台邮箱托管服务（R72，2026-09-03 爸爸拍板：ClawEmail 归 M 平台托管——知夏管理面、米娅使用面）。

铁律（米娅 8/24 回信风暴教训，写死在本模块）：
- 只手动收发，绝无 gateway/轮询/自动回复；本模块不驻留任何后台线程。
- 凭据只从 .settings_secrets 读（email.account.<名字>.password / email.home.<id>.apiKey），源码零密钥。
- 主机钉死官方端点：IMAP claw.163.com:993 / SMTP claw.163.com:25（STARTTLS），不跟随任何外来 URL。
- 多主账号=注册表按 home 归属、按名字寻址（爸爸"按名字查零机制"令）——OWUI 时代双主账号管不明白的根因是
  一个网关守护管一摊，这里无守护、无状态，加账号=注册表加一行。
"""
import imaplib
import json
import smtplib
from email.mime.text import MIMEText
from email.header import decode_header, make_header
import email as _email

IMAP_HOST, IMAP_PORT = "claw.163.com", 993
SMTP_HOST, SMTP_PORT = "claw.163.com", 25


def accounts() -> list:
    from settings_mgr import load_settings
    return [a for a in ((load_settings().get("email", {}) or {}).get("accounts") or []) if isinstance(a, dict)]


def _acct(name: str):
    acc = next((a for a in accounts() if a.get("name") == name), None)
    if acc is None:
        raise ValueError(f"邮箱账号「{name}」不在注册表（设置页 email 节 / 找 Celia 加）")
    if acc.get("enabled") is False:
        raise ValueError(f"邮箱「{name}」已被停用")
    pw = ""
    if acc.get("transport") != "cli":  # r35：cli 通道账号钥匙在沙箱，平台侧不需要授权码
        from settings_mgr import secret_get
        pw = secret_get(f"email.account.{name}.password") or ""
        if not pw:
            raise ValueError(f"邮箱「{name}」缺授权码（email.account.{name}.password）")
    return acc, pw


def _imap():
    """R73（NOVA🟡）：统一构造 IMAP4_SSL——显式默认 TLS 上下文（校验证书）+ 30s 超时。"""
    import ssl
    return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=30)


# ── r35（09-27 爸爸诊断）：transport=cli 通道 ──────────────────────────────
# 米娅的新箱 miafirm@claw.163.com 是 ClawEmail 智能体信箱：正门=官方 mail-cli（WS/ajax），
# 钥匙住在米娅沙箱的 mail-cli 配置里——平台代码与注册表【零凭据】。
# 牛马（总管等）收发 = 经此桥借道主人的活通道（米娅下令查收=授权本身）。
# 旧 IMAP 路（email.account.<名>.password 16 位码）保留给仍走协议门的账号。
import re as _re

_UID_RE = _re.compile(r"^[0-9]{1,4}:[A-Za-z0-9+/=_-]{1,64}$")   # 57:1tbi... 形态，拒一切 shell 拼接面
_ADDR_RE = _re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _cli_exec(name: str, args: str, timeout: int = 40, raw: str = "") -> str:
    """在米娅沙箱里跑 mail-cli --json <args>（复用 SandboxedShellBackend 现成执行器：
    票据/401 重试/超时击杀全走官方路，这里不造第二套）。raw=完整命令（send 用）。"""
    from mia_agent.sandbox import SandboxedShellBackend
    be = SandboxedShellBackend(root_dir="/tmp")
    cmd = raw if raw else ("mail-cli --profile default --json " + args)
    r = be._call(cmd, timeout)
    if r.exit_code != 0:
        raise RuntimeError(f"信箱通道返回异常（exit={r.exit_code}）：{r.output[:300]}")
    return r.output


def _cli_json(name: str, args: str, timeout: int = 40, raw: str = ""):
    raw_out = _cli_exec(name, args, timeout, raw=raw)
    i = raw_out.find("{")
    j = raw_out.find("[")
    if 0 <= j < i:
        i = j
    if i < 0:
        raise RuntimeError(f"信箱通道无结构化输出：{raw_out[:200]}")
    return json.loads(raw_out[i:])


def check_cli(name: str, limit: int = 8) -> str:
    d = _cli_json(name, f"mail list --fid 1 --order date --desc --limit {int(limit)}")
    rows = d.get("data") or []
    if not rows:
        return f"邮箱「{name}」收件箱没有信。"
    out = [f"邮箱「{name}」最近 {len(rows)} 封（编号 已读性 | 日期 | 发件人 | 主题）："]
    for m in rows:
        out.append(f"  {m.get('id','?')} | {'未读' if not m.get('read') else '已读'} | {m.get('date','')} | {m.get('from','')} | {m.get('subject','')}")
    return "\n".join(out)


def read_cli(name: str, uid: str) -> str:
    if not _UID_RE.match(uid or ""):
        return "uid 格式不对——请用 check 列表里的编号原样复制。"
    d = _cli_json(name, f"read body --fid 1 --id '{uid}'")
    r = d.get("data") or d
    body = str(r.get("body") or r.get("text") or "")[:6000]
    return f"【{r.get('subject','')}】来自 {r.get('from','')} {r.get('date','')}\n{body}"


def send_cli(name: str, to: str, subject: str, body: str) -> str:
    for t in (to or "").split(","):
        if t.strip() and not _ADDR_RE.match(t.strip()):
            return f"收件地址格式不合法：{t.strip()[:60]}"
    import base64 as _b64
    b64 = _b64.b64encode((body or "").encode("utf-8")).decode()
    # 正文走 base64 落盘（防注入/防引号炸）；收件人与主题做 shell 安全转义后用双引号包
    to_q = (to or "").replace('"', "").replace("$", "").replace("`", "")
    subj_q = (subject or "").replace('"', "").replace("$", "").replace("`", "")[:120]
    full = (f"printf %s {b64} | base64 -d > /tmp/mia_mail_body.txt && "
            f'mail-cli --profile default --json compose send --to "{to_q}" --subject "{subj_q}" '
            f"--body-file /tmp/mia_mail_body.txt; rm -f /tmp/mia_mail_body.txt")
    d = _cli_json(name, "", timeout=60, raw=full)
    ok = d.get("success") or (d.get("data") or {}).get("status") == "sent"
    return f"已发往 {to}：{subject}" if ok else f"发送失败：{str(d)[:200]}"


def check(name: str, limit: int = 8) -> str:
    if _acct(name)[0].get("transport") == "cli":
        return check_cli(name, limit)
    """列最近 N 封（只读不动邮件、不回复）。
    R73（Cora P3a）：用 UID 命令取真实 UID——check 与 read 是两次独立连接，
    若用序号（sequence number），中间外部删信会导致序号漂移读错信；UID 稳定。"""
    acc, pw = _acct(name)
    M = _imap()
    try:
        M.login(acc["address"], pw)
        M.select("INBOX")
        typ, data = M.uid("search", None, "ALL")
        ids = data[0].split()
        out = [f"📮 {acc['address']}：共 {len(ids)} 封，最近 {min(limit, len(ids))} 封（新→旧）："]
        for i in ids[-limit:][::-1]:
            typ, d = M.uid("fetch", i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            raw = d[0][1] if d and d[0] and isinstance(d[0], tuple) else b""
            out.append(f"  [{i.decode()}] {_h(raw, 'Date')[:16]} | 来自 {_h(raw, 'From')[:36]} | {_h(raw, 'Subject')[:44]}")
        return "\n".join(out)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def _h(raw: bytes, key: str) -> str:
    # MIME 折行修复：长 header 值会 \r\n+空白 续行，先展开再逐行找（否则只截到首段、decode 失败露生码）
    import re as _re
    unfolded = _re.sub(rb"\r\n[ \t]+", b" ", raw, flags=_re.I)
    for line in unfolded.split(b"\r\n"):
        if line.lower().startswith((key + ":").encode().lower()):
            v = line.split(b":", 1)[1].strip().decode("ascii", "replace")  # decode_header 只收 str（自查实锤的 bytes 坑）
            try:
                return str(make_header(decode_header(v)))
            except Exception:
                return v
    return ""


def read(name: str, uid: str) -> str:
    # r36q（Veda"根读取分裂成立"判词）：cli 分流收进库层，read/send 与 check 同口径
    if _acct(name)[0].get("transport") == "cli":
        if not _UID_RE.match(uid or ""):
            return "uid 格式不对——请用 check 列表里的编号原样复制。"
        return read_cli(name, uid)
    """读单封全文（只读）。"""
    # R73（Cora P2 实锤）：uid 直接进 IMAP 命令行、imaplib._command 零过滤——
    # 白名单只认纯数字，比消毒可靠。提示注入让米娅传 "1\r\nXXXX LOGOUT" 也进不去。
    if not str(uid).isdigit():
        return "❌ uid 必须是 check 列表里 [方括号] 内的纯数字编号"
    acc, pw = _acct(name)
    M = _imap()
    try:
        M.login(acc["address"], pw)
        M.select("INBOX")
        typ, d = M.uid("fetch", str(uid).encode(), "(BODY.PEEK[])")
        raw = d[0][1] if d and d[0] and isinstance(d[0], tuple) else b""
        msg = _email.message_from_bytes(raw)
        body = ""
        if msg.is_multipart():
            for p in msg.walk():
                if p.get_content_type() == "text/plain":
                    body = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
                    break
        else:
            pl = msg.get_payload(decode=True)
            body = pl.decode(msg.get_content_charset() or "utf-8", "replace") if pl else ""
        def dec(x):
            try:
                return str(make_header(decode_header(x or "")))
            except Exception:
                return x or ""
        return f"📖 {acc['address']} UID {uid}\n来自: {dec(msg['From'])}\n主题: {dec(msg['Subject'])}\n时间: {msg['Date']}\n\n{body[:3000]}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def send(name: str, to: str, subject: str, body: str) -> str:
    if _acct(name)[0].get("transport") == "cli":
        return send_cli(name, to, subject, body)
    """手动发信（一封一发；绝不自动回复任何来信）。"""
    acc, pw = _acct(name)
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = acc["address"]
    msg["To"] = to
    msg["Subject"] = subject
    import ssl
    s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        s.starttls(context=ssl.create_default_context())
        s.login(acc["address"], pw)
        s.sendmail(acc["address"], [to], msg.as_string())
        return f"✅ 已发：{subject} → {to}（经 {acc['address']}）"
    finally:
        try:
            s.quit()
        except Exception:
            pass
