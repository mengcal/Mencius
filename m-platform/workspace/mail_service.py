"""M平台邮箱托管服务（R72，2026-09-03 管理员拍板：ClawEmail 归 M 平台托管——作者管理面、助手使用面）。

铁律（助手 8/24 回信风暴教训，写死在本模块）：
- 只手动收发，绝无 gateway/轮询/自动回复；本模块不驻留任何后台线程。
- 凭据只从 .settings_secrets 读（email.account.<名字>.password / email.home.<id>.apiKey），源码零密钥。
- 主机钉死官方端点：IMAP claw.163.com:993 / SMTP claw.163.com:25（STARTTLS），不跟随任何外来 URL。
- 多主账号=注册表按 home 归属、按名字寻址（管理员"按名字查零机制"令）——open-webui 时代双主账号管不明白的根因是
  一个网关守护管一摊，这里无守护、无状态，加账号=注册表加一行。
"""
import imaplib
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
        raise ValueError(f"邮箱账号「{name}」不在注册表（设置页 email 节 / 找作者加）")
    if acc.get("enabled") is False:
        raise ValueError(f"邮箱「{name}」已被停用")
    from settings_mgr import secret_get
    pw = secret_get(f"email.account.{name}.password") or ""
    if not pw:
        raise ValueError(f"邮箱「{name}」缺授权码（email.account.{name}.password）")
    return acc, pw


def _imap():
    """R73（评审B🟡）：统一构造 IMAP4_SSL——显式默认 TLS 上下文（校验证书）+ 30s 超时。"""
    import ssl
    return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=30)


def check(name: str, limit: int = 8) -> str:
    """列最近 N 封（只读不动邮件、不回复）。
    R73（评审A P3a）：用 UID 命令取真实 UID——check 与 read 是两次独立连接，
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
    """读单封全文（只读）。"""
    # R73（评审A P2 实锤）：uid 直接进 IMAP 命令行、imaplib._command 零过滤——
    # 白名单只认纯数字，比消毒可靠。提示注入让助手传 "1\r\nXXXX LOGOUT" 也进不去。
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
