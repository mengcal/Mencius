# -*- coding: utf-8 -*-
"""收评审回信：拉取知夏信箱最新信件存 notes/reviews/2026-09-07-r20/（只收不发）。"""
import imaplib
import email
from email.header import decode_header
from pathlib import Path
import re

IMAP_HOST = "claw.163.com"
USER = "mencius.celia@claw.163.com"
PWD = "GVN8y4ar7KR664Hs"
OUT = Path(r"D:\glm\projects\notes\reviews\2026-09-07-r20")
OUT.mkdir(parents=True, exist_ok=True)


def dec(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for t, enc in parts:
        if isinstance(t, bytes):
            out += t.decode(enc or "utf-8", "replace")
        else:
            out += t
    return out


m = imaplib.IMAP4_SSL(IMAP_HOST)
m.login(USER, PWD)
m.select("INBOX")
typ, data = m.search(None, "ALL")
ids = data[0].split()
print("信箱共", len(ids), "封，取最新 12 封检查：")
saved = []
for i in ids[-12:]:
    typ, md = m.fetch(i, "(RFC822)")
    raw = md[0][1]
    msg = email.message_from_bytes(raw)
    frm = dec(msg.get("From", ""))
    subj = dec(msg.get("Subject", ""))
    date = msg.get("Date", "")
    print(f"  [{i.decode()}] {date[:22]} | {frm[:40]} | {subj[:60]}")
    if re.search(r"r20|围剿|评审|检测|报告", subj + frm):
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                    break
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
        else:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "replace")
        fn = re.sub(r'[\\/:*?"<>|]', "_", f"{date[:16]}_{frm.split('@')[0]}_{subj[:40]}.txt")
        (OUT / fn.strip()).write_text(f"From: {frm}\nDate: {date}\nSubject: {subj}\n\n{body}",
                                      encoding="utf-8")
        saved.append(fn.strip())
m.logout()
print("\n已存", len(saved), "封到", OUT)
for s in saved:
    print("  -", s)
