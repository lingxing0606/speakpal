"""出站请求的地址检查（防 SSRF）。

模型 / 语音合成的 base_url 可以由浏览器请求头指定，等于让用户决定服务端去请求哪里。
不检查的话，填 http://127.0.0.1:8000 或云主机元数据地址 169.254.169.254
就能让服务端替攻击者访问内网。这里在发请求前把主机名解析出来，
任何一个解析结果落在内网 / 本机 / 链路本地 / 保留段就拒绝。

已知局限：解析和真正连接之间存在 DNS 重绑定窗口；演示级项目可接受。
本机跑 Ollama 等需要访问 127.0.0.1 时，设 ALLOW_PRIVATE_LLM_HOSTS=1。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from ..config import settings


class UnsafeBaseURL(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_base_url(value: str) -> None:
    """不安全就抛 UnsafeBaseURL；通过则什么也不返回。"""
    try:
        parsed = urlparse(value)
    except ValueError:
        raise UnsafeBaseURL("Base URL 格式不正确")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeBaseURL("Base URL 不是 http(s) 地址")
    if settings.allow_private_llm_hosts:
        return
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError):
        raise UnsafeBaseURL("Base URL 的域名无法解析")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        except ValueError:
            raise UnsafeBaseURL("Base URL 解析出无法识别的地址")
        if _blocked(ip):
            raise UnsafeBaseURL("Base URL 指向内网或本机地址，已拒绝（本机模型请设 ALLOW_PRIVATE_LLM_HOSTS=1）")
