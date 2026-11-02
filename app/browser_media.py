"""
文件: browser_media.py
模块: 浏览器媒体获取
功能: 使用系统 Chrome 的 DevTools 协议打开平台页面并捕获真实媒体资源。
依赖: Python 标准库、系统 Chrome/Chromium。
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class BrowserMediaError(RuntimeError):
    """浏览器页面无法提供真实媒体时的可读错误。"""

    def __init__(self, message: str, code: str = "browser_media_failed") -> None:
        """
        功能: 保存浏览器媒体错误及机器可读错误码。

        参数:
            message (str): 面向内部日志和回退逻辑的错误描述。
            code (str): 用于区分浏览器不可用、无媒体等情况的错误码。

        返回:
            None: 初始化错误对象。
        """
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BrowserMediaResult:
    """浏览器捕获的媒体文件及页面元数据，不包含 Cookie。"""

    path: Path
    title: str
    source_url: str
    video_id: str | None
    uploader: str | None


def find_browser_executable() -> str | None:
    """
    功能: 查找本机可用于 CDP 的 Chromium 浏览器。

    参数:
        None: 浏览器路径从系统安装位置和 PATH 自动发现。

    返回:
        str | None: 可执行文件路径，未发现时返回 None。
    """
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    elif sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA", "")
        program = os.getenv("PROGRAMFILES", "")
        candidates.extend(
            [
                str(Path(local) / "Google/Chrome/Application/chrome.exe"),
                str(Path(program) / "Google/Chrome/Application/chrome.exe"),
                str(Path(local) / "Microsoft/Edge/Application/msedge.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/microsoft-edge",
            ]
        )
    candidates.extend(shutil.which(name) or "" for name in ("google-chrome", "chromium", "chromium-browser", "msedge"))
    return next((path for path in candidates if path and Path(path).is_file()), None)


def _browser_cookies(cookiejar) -> list[dict]:
    """
    功能: 将内存 Cookie 容器转换成 CDP Network.setCookies 格式。

    参数:
        cookiejar: yt-dlp 返回的 CookieJar，仅在当前下载进程内存中存在。

    返回:
        list[dict]: 可传给 Chrome 的 Cookie 字段，不落盘。
    """
    cookies: list[dict] = []
    for cookie in cookiejar or []:
        if not cookie.domain or not cookie.name:
            continue
        item = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
        }
        if cookie.expires:
            item["expires"] = float(cookie.expires)
        rest = getattr(cookie, "_rest", {}) or {}
        if any(str(key).lower() == "httponly" for key in rest):
            item["httpOnly"] = True
        same_site = next((str(value).lower() for key, value in rest.items() if str(key).lower() == "samesite"), "")
        if same_site in {"strict", "lax", "none"}:
            item["sameSite"] = same_site.capitalize()
        cookies.append(item)
    return cookies


def _safe_filename_extension(content_type: str, media_url: str) -> str:
    """
    功能: 根据媒体响应类型选择安全文件扩展名。

    参数:
        content_type (str): 媒体响应的 Content-Type。
        media_url (str): 捕获到的媒体 URL，仅用于扩展名兜底。

    返回:
        str: 带点的文件扩展名。
    """
    lowered = content_type.lower()
    if "webm" in lowered:
        return ".webm"
    if "m4a" in lowered or "mp4a" in lowered or "audio" in lowered:
        return ".m4a"
    if "mpeg" in lowered:
        return ".mp3"
    if "mp4" in lowered:
        return ".mp4"
    match = re.search(r"\.(mp4|m4a|webm|mp3)(?:[?#]|$)", media_url.lower())
    return f".{match.group(1)}" if match else ".mp4"


def _extract_video_id(url: str) -> str | None:
    """
    功能: 从最终页面 URL 提取常见平台的视频或笔记 ID。

    参数:
        url (str): 浏览器最终落地 URL。

    返回:
        str | None: 平台 ID，无法识别时返回 None。
    """
    patterns = (r"/(?:video|note)/(\d+)", r"/video/(BV[\w]+)", r"/(BV[\w]+)")
    return next((match.group(1) for pattern in patterns if (match := re.search(pattern, url, re.IGNORECASE))), None)


def _clean_title(title: str) -> str:
    """
    功能: 清理平台页面标题中的站点后缀。

    参数:
        title (str): 页面标题。

    返回:
        str: 可用于摘要标题的短文本。
    """
    cleaned = re.sub(r"\s*[-|｜]\s*(抖音|哔哩哔哩|bilibili|小红书)\s*$", "", title, flags=re.IGNORECASE)
    return cleaned.strip() or "视频内容"


def _ws_frame(payload: str) -> bytes:
    """
    功能: 编码客户端 WebSocket 文本帧。

    参数:
        payload (str): 要发送的 JSON 文本。

    返回:
        bytes: 已掩码的 WebSocket 帧。
    """
    data = payload.encode("utf-8")
    mask = os.urandom(4)
    length = len(data)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    elif length < 65_536:
        header = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big")
    return header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(data))


class _CdpConnection:
    """最小 CDP WebSocket 客户端，避免额外安装浏览器驱动。"""

    def __init__(self, websocket_url: str) -> None:
        """
        功能: 建立 Chrome DevTools WebSocket 连接。

        参数:
            websocket_url (str): /json/list 返回的页面 WebSocket 地址。

        返回:
            None: 初始化连接。
        """
        parsed = urllib.parse.urlparse(websocket_url)
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self._read_until(b"\r\n\r\n")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise OSError("Chrome DevTools WebSocket 握手失败")
        self.next_id = 0
        self.events: list[dict] = []

    def _read_until(self, marker: bytes) -> bytes:
        """功能: 读取 HTTP 握手头；marker 为结束标识；返回头部字节。"""
        chunks = bytearray()
        while marker not in chunks:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("Chrome DevTools 连接已关闭")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_frame(self, timeout: float = 1.0) -> tuple[int, bytes]:
        """功能: 读取一个 WebSocket 帧；timeout 为秒数；返回操作码和负载。"""
        self.sock.settimeout(timeout)
        first = self.sock.recv(2)
        if len(first) != 2:
            raise OSError("Chrome DevTools 帧不完整")
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self.sock.recv(2), "big")
        elif length == 127:
            length = int.from_bytes(self.sock.recv(8), "big")
        mask = self.sock.recv(4) if first[1] & 0x80 else None
        payload = bytearray()
        while len(payload) < length:
            payload.extend(self.sock.recv(min(65_536, length - len(payload))))
        if mask:
            payload = bytearray(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, bytes(payload)

    def _receive(self, timeout: float = 1.0) -> dict | None:
        """功能: 接收一条 CDP 消息；timeout 为秒数；返回 JSON 消息或 None。"""
        try:
            opcode, payload = self._read_frame(timeout)
        except socket.timeout:
            return None
        if opcode == 9:
            self.sock.sendall(bytes([0x8A, len(payload)]) + payload)
            return None
        if opcode in {8, 10} or opcode != 1:
            return None
        return json.loads(payload.decode("utf-8"))

    def command(self, method: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        """
        功能: 发送 CDP 命令并等待对应结果，同时保留异步事件。

        参数:
            method (str): CDP 方法名。
            params (dict | None): CDP 方法参数。
            timeout (float): 等待结果的秒数。

        返回:
            dict: CDP 命令的 result 字段。
        """
        self.next_id += 1
        command_id = self.next_id
        self.sock.sendall(_ws_frame(json.dumps({"id": command_id, "method": method, "params": params or {}})))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._receive(min(1.0, max(0.05, deadline - time.monotonic())))
            if not message:
                continue
            if "id" not in message:
                self.events.append(message)
                continue
            if message["id"] != command_id:
                continue
            if "error" in message:
                raise OSError(str(message["error"]))
            return message.get("result", {})
        raise TimeoutError(f"等待 CDP 命令超时: {method}")

    def drain(self, seconds: float) -> None:
        """功能: 持续接收页面事件；seconds 为等待秒数；返回无。"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            message = self._receive(min(0.5, max(0.05, deadline - time.monotonic())))
            if message and "id" not in message:
                self.events.append(message)

    def close(self) -> None:
        """功能: 关闭 WebSocket 和底层 socket；参数无；返回无。"""
        try:
            self.sock.close()
        except OSError:
            pass


def _start_chrome(executable: str) -> tuple[subprocess.Popen, _CdpConnection, Path]:
    """
    功能: 启动隔离 Chrome 并连接一个空白页面。

    参数:
        executable (str): Chrome 可执行文件路径。

    返回:
        tuple: Chrome 进程、CDP 连接和临时用户目录。
    """
    port_socket = socket.socket()
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()
    profile_dir = Path(tempfile.mkdtemp(prefix="video-ai-browser-"))
    process = subprocess.Popen(
        [
            executable,
            "--headless=new",
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-extensions",
            "--disable-sync",
            "--disable-popup-blocking",
            "--disable-blink-features=AutomationControlled",
            "--mute-audio",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    pages = json.loads(response.read().decode("utf-8"))
                page = next((item for item in pages if item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
                if page:
                    return process, _CdpConnection(page["webSocketDebuggerUrl"]), profile_dir
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.25)
        raise BrowserMediaError("Chrome 调试页面启动超时", "browser_runtime_timeout")
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise


def _evaluate(connection: _CdpConnection, expression: str):
    """
    功能: 执行页面 JavaScript 并返回可序列化值。

    参数:
        connection (_CdpConnection): 当前页面的 CDP 连接。
        expression (str): 要执行的 JavaScript 表达式。

    返回:
        object: 页面返回值，执行失败时返回 None。
    """
    try:
        result = connection.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result.get("result", {}).get("value")
    except (OSError, TimeoutError):
        return None


def _cookie_header(cookies: list[dict], target_url: str) -> str:
    """
    功能: 按目标媒体域名筛选浏览器 Cookie 请求头。

    参数:
        cookies (list[dict]): CDP 返回的临时 Cookie 元数据和值。
        target_url (str): 媒体请求 URL。

    返回:
        str: 仅匹配目标域名和路径的 Cookie 头。
    """
    parsed = urllib.parse.urlparse(target_url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    pairs = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        cookie_path = cookie.get("path") or "/"
        if domain and not (host == domain or host.endswith(f".{domain}")):
            continue
        if not path.startswith(cookie_path):
            continue
        pairs.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(pairs)


def _download_candidate(media_url: str, output_dir: Path, headers: dict[str, str]) -> tuple[Path, str] | None:
    """
    功能: 使用浏览器会话头下载一个候选媒体 URL。

    参数:
        media_url (str): 页面实际请求过的媒体地址。
        output_dir (Path): 当前任务临时目录。
        headers (dict[str, str]): Referer、User-Agent 和 Cookie 请求头。

    返回:
        tuple[Path, str] | None: 成功时返回媒体路径和响应类型。
    """
    request = urllib.request.Request(media_url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            content_type = response.headers.get("Content-Type", "")
            content_length = int(response.headers.get("Content-Length", "0") or 0)
            if content_length > 500 * 1024 * 1024:
                raise BrowserMediaError("视频文件超过 500 MB 限制", "media_too_large")
            extension = _safe_filename_extension(content_type, media_url)
            temporary = output_dir / f"source{extension}.part"
            total = 0
            with temporary.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 500 * 1024 * 1024:
                        temporary.unlink(missing_ok=True)
                        raise BrowserMediaError("视频文件超过 500 MB 限制", "media_too_large")
                    stream.write(chunk)
            if total < 16_384:
                temporary.unlink(missing_ok=True)
                return None
            media_path = output_dir / f"source{extension}"
            temporary.replace(media_path)
            return media_path, content_type
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None


def fetch_with_browser(
    url: str,
    output_dir: Path,
    cookiejar,
    publish: Callable[..., None],
    timeout_ms: int = 120_000,
) -> BrowserMediaResult:
    """
    功能: 打开真实平台页面并下载页面实际请求的媒体文件。

    参数:
        url (str): 用户提交的原始平台 URL。
        output_dir (Path): 当前任务的临时输出目录。
        cookiejar: 已在隔离工作进程中解密的内存 Cookie 容器。
        publish (Callable[..., None]): 写入安全处理进度的函数。
        timeout_ms (int): 页面和媒体请求的总超时时间上限。

    返回:
        BrowserMediaResult: 媒体路径、标题和页面真实元数据。

    异常:
        BrowserMediaError: Chrome 不可用、页面没有媒体或媒体下载失败。
    """
    executable = find_browser_executable()
    if not executable:
        raise BrowserMediaError("未发现可用的 Chrome/Chromium 浏览器", "browser_executable_missing")

    publish(stage="browser_media", message="正在打开本机浏览器会话并等待视频资源", cookie_count=len(cookiejar or []))
    process = None
    connection = None
    profile_dir = None
    try:
        process, connection, profile_dir = _start_chrome(executable)
        connection.command("Network.enable")
        connection.command("Page.enable")
        connection.command(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
        )
        if cookiejar:
            connection.command("Network.setCookies", {"cookies": _browser_cookies(cookiejar)})
        connection.command("Page.navigate", {"url": url}, timeout=30)
        deadline = time.monotonic() + min(timeout_ms / 1000, 55)
        connection.drain(4)
        _evaluate(connection, "document.querySelector('video')?.play().catch(() => null)")
        while time.monotonic() < deadline:
            connection.drain(1)
            if any(event.get("method") == "Page.loadEventFired" for event in connection.events):
                if time.monotonic() + 5 < deadline:
                    connection.drain(5)
                break
        media_events = []
        for event in connection.events:
            if event.get("method") != "Network.responseReceived":
                continue
            response = event.get("params", {}).get("response", {})
            media_url = response.get("url", "")
            mime_type = str(response.get("mimeType", "")).lower()
            resource_type = event.get("params", {}).get("type", "")
            is_media = resource_type == "Media" or mime_type.startswith(("video/", "audio/"))
            is_media = is_media or any(token in media_url.lower() for token in (".mp4", ".m4a", ".webm", "video/tos", "mime_type=video"))
            if 200 <= response.get("status", 0) < 400 and is_media:
                media_events.append({"url": media_url, "size": response.get("encodedDataLength", 0), "mime": mime_type})
        if not media_events:
            raise BrowserMediaError("页面已打开但未捕获到真实视频资源，请确认视频可以在浏览器中播放", "browser_media_not_found")

        try:
            browser_cookies = connection.command("Network.getAllCookies").get("cookies", [])
        except (OSError, TimeoutError):
            browser_cookies = []
        user_agent = _evaluate(connection, "navigator.userAgent") or "Mozilla/5.0"
        final_url = _evaluate(connection, "location.href") or url
        headers = {"Referer": final_url, "User-Agent": user_agent, "Accept": "*/*"}
        ordered = sorted(
            {item["url"]: item for item in media_events}.values(),
            key=lambda item: (0 if item["mime"].startswith("audio/") else 1, -item["size"]),
        )
        for candidate in ordered[:6]:
            headers["Cookie"] = _cookie_header(browser_cookies, candidate["url"])
            publish(stage="browser_media", message="正在保存浏览器实际播放的媒体", cookie_count=len(cookiejar or []))
            result = _download_candidate(candidate["url"], output_dir, headers)
            if result:
                media_path, _ = result
                title = _clean_title(_evaluate(connection, "document.title") or "视频内容")
                return BrowserMediaResult(media_path, title, final_url, _extract_video_id(final_url), None)
        raise BrowserMediaError("浏览器找到了视频请求，但媒体下载未完成，请稍后重试", "browser_media_download_failed")
    except BrowserMediaError:
        raise
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise BrowserMediaError("浏览器自动获取失败，请确认浏览器可正常打开该视频", "browser_runtime_failed") from error
    finally:
        if connection:
            connection.close()
        if process:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)

