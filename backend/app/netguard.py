"""Fetch student-supplied URLs (calendar feeds) without letting them reach the server's private network.

Every hop of a redirect chain must be https and resolve only to public addresses. Set
ALLOW_PRIVATE_FEEDS=true for local testing against a feed served from this machine.
"""

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 4
MAX_BYTES = 5 * 1024 * 1024


class UnsafeURL(ValueError):
    pass


def _allow_private() -> bool:
    return os.getenv("ALLOW_PRIVATE_FEEDS", "false").lower() == "true"


def check_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise UnsafeURL("Use the full https:// link to the calendar feed.")
    if parsed.scheme == "http" and not _allow_private():
        raise UnsafeURL("Only https:// calendar links are accepted.")
    if _allow_private():
        return url.strip()
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL("That address couldn't be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnsafeURL("That link points to a private network address.")
    return url.strip()


def safe_get(url: str, timeout: float = 20) -> httpx.Response:
    current = check_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = client.get(current, headers={"User-Agent": "UniTask calendar sync"})
            if response.is_redirect and response.headers.get("location"):
                current = check_url(urljoin(current, response.headers["location"]))
                continue
            if len(response.content) > MAX_BYTES:
                raise UnsafeURL("That calendar feed is too large.")
            return response
    raise UnsafeURL("Too many redirects.")
