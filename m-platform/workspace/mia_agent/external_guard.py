# -*- coding: utf-8 -*-
"""external_guard —— 对外派活一期安全核（圆桌方案 v3 §三-4 落地，r58）。

SSRF 十面（R10.x 评审全收）：
  1. 协议白名单 http/https（拒 file/gopher/data…）
  2. 解析后逐 IP 判：仅允许环回（127.0.0.0/8、::1）——外部智能体=本机 CodeBuddy/webhook 岗，
     拒私网(10/172.16-31/192.168)/链路本地(169.254=云元数据)/组播/保留
  3. 端口白名单（爸爸登记时手填，非 80/443 默认）
  4. 防 DNS rebinding：校验与连接分离——validate 返回 pin_ip，调用方必须连 pin 的 IP
     （Host 头留原域名），不给二次解析机会
  5. 禁重定向（httpx follow_redirects=False，常量下发）
HKDF 子钥（一岗一钥）：master_key 经 HKDF-SHA256(info=岗位名) 派生子钥——
  外部岗持子钥回调，泄露只伤单岗；master 永不出平台。
一期边界：只接本机环回岗（CodeBuddy webhook 岗）；公网外部=二期跟 A2A 官方标准再开。
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

ALLOWED_PORTS_DEFAULT = ()  # 登记时由爸爸指定端口白名单
NO_REDIRECT = False          # httpx follow_redirects 用这个常量，禁跟随


class ExternalUrlError(ValueError):
    """URL 校验拒绝（消息可直接给米娅/日志，不回显内部拓扑细节过多）。"""


def validate_url(url: str, allowed_ports: tuple) -> dict:
    """返回 {"ip": 钉定IP, "port": int, "host": 原host, "scheme": ...}；不合格 raise。"""
    u = urlparse(url or "")
    if u.scheme not in ("http", "https"):
        raise ExternalUrlError("协议仅限 http/https")
    host = u.hostname or ""
    if not host:
        raise ExternalUrlError("缺主机名")
    port = u.port or (443 if u.scheme == "https" else 80)
    if port not in tuple(allowed_ports or ()):
        raise ExternalUrlError("端口不在该岗登记白名单内")
    # 字面 IP 也要过检；域名解析后每个 IP 都要过检（rebinding 面）
    try:
        import socket
        if re.fullmatch(r"[\d.]+|([0-9a-fA-F:]+)", host):
            infos = [(None, None, None, None, (host, 0, 0, 0)) if ":" not in host
                     else (None, None, None, None, (host, 0, 0, 0))]
            ips = [host]
        else:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            ips = list({i[4][0] for i in infos})
    except Exception:
        raise ExternalUrlError("主机解析失败")
    pinned = None
    for s in ips:
        ip = ipaddress.ip_address(s)
        # r58 毒例自炸修正：127/8 在 ipaddress 语义里 is_private=True——
        # 环回是本期唯一允许项，必须先放行再谈其他（顺序错=把 127.0.0.1 自己拒了）
        if ip.is_loopback:
            pinned = pinned or s
            continue
        if (ip.is_link_local or ip.is_private or ip.is_multicast
                or ip.is_reserved or not ip.is_global and not ip.is_loopback):
            raise ExternalUrlError("一期仅允许本机环回（公网/私网/链路本地全拒）")
    if not pinned:
        raise ExternalUrlError("无可用环回地址")
    return {"ip": pinned, "port": port, "host": host, "scheme": u.scheme}


def hkdf_subkey(master_key: bytes, post_name: str) -> bytes:
    """HKDF-SHA256 子钥派生（32B）。cryptography 件在容器已具备（providers 链）。"""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32,
                salt=b"mia-external-v1",
                info=("post:" + post_name).encode("utf-8"))
    return hkdf.derive(master_key)


def ssrf_pinned_request_kwargs(checked: dict) -> dict:
    """给调用方（httpx）的连接参数：连钉定 IP、Host 头留原域名——rebinding 防线落地件。"""
    return {
        "extensions": {"sni_hostname": checked["host"]},
        # httpx 用 transport 级 IP 钉定或 URL 改写：调用方以
        # url.replace(host, ip) + headers Host 执行（一期调用点唯一，见 dispatch）
    }
