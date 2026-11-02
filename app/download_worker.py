"""文件: download_worker.py；模块: 隔离下载进程；功能: 解密并仅使用目标平台会话下载媒体；依赖: yt-dlp。"""

import json
import sys
import time
from pathlib import Path

from .browser_media import BrowserMediaError, fetch_with_browser
from .inputs import PlatformDetector
from .platform_cookies import extract_platform_cookies


class QuietLogger:
    """抑制下载器原始日志，防止 URL 参数或会话信息出现在接口和终端中。"""

    def debug(self, message: str) -> None:
        """功能: 忽略日志；message 为下载器日志；返回无。"""

    warning = debug
    error = debug
    info = debug


def publish(path: Path, **fields: str | int | float) -> None:
    """功能: 原子写入进度；path 为临时状态路径，fields 为非敏感进度字段；返回无。"""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def run_download(payload: dict) -> None:
    """功能: 执行一次下载；payload 为链接、配置和输出路径；结果仅输出媒体元数据，不输出 Cookie。"""
    from yt_dlp import YoutubeDL

    output_dir = Path(payload["output_dir"])
    progress_path = output_dir / "progress.json"
    platform = PlatformDetector.detect(payload["url"])
    cookie_count = 0
    browser = payload.get("browser")
    cookiejar = None
    if browser:
        publish(progress_path, stage="browser", message=f"正在读取 {browser} 的 {payload['profile']} 会话；如出现系统钥匙串提示，请在本机授权")
        try:
            cookiejar = extract_platform_cookies(browser, payload["profile_path"], platform, QuietLogger())
        except Exception:
            print(json.dumps({"error_code": "browser_access_failed", "error": "无法读取浏览器会话，请确认浏览器权限与系统钥匙串授权"}), flush=True)
            return
        domains = PlatformDetector.domains.get(platform, ())
        for cookie in list(cookiejar):
            host = cookie.domain.lstrip(".")
            if not any(host == domain or host.endswith(f".{domain}") for domain in domains) or cookie.is_expired(time.time()):
                cookiejar.clear(cookie.domain, cookie.path, cookie.name)
        cookie_count = len(cookiejar)
        if cookie_count == 0:
            print(json.dumps({"error_code": "browser_session_empty", "error": "未能读取有效的平台会话，请在所选浏览器中打开目标视频后重试"}), flush=True)
            return

    platform = PlatformDetector.detect(payload["url"])
    if payload.get("browser_automation") and platform in {"douyin", "bilibili", "xiaohongshu"}:
        try:
            browser_result = fetch_with_browser(payload["url"], output_dir, cookiejar, lambda **fields: publish(progress_path, **fields))
            print(json.dumps({"path": str(browser_result.path), "title": browser_result.title, "video_id": browser_result.video_id, "uploader": browser_result.uploader, "source_url": browser_result.source_url, "cookie_count": cookie_count}, ensure_ascii=False), flush=True)
            return
        except BrowserMediaError as error:
            publish(progress_path, stage="download", message="浏览器媒体获取未完成，正在使用下载器回退", cookie_count=cookie_count)
            if error.code in {"media_too_large"}:
                print(json.dumps({"error_code": error.code, "error": str(error), "cookie_count": cookie_count}, ensure_ascii=False), flush=True)
                return

    publish(progress_path, stage="download", message="正在解析链接并获取原视频", cookie_count=cookie_count)
    options = {
        "format": "bestaudio/best[height<=720]/best",
        "outtmpl": str(output_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "socket_timeout": 12,
        "retries": 1,
        "extractor_retries": 1,
        "fragment_retries": 1,
        "max_filesize": 500 * 1024 * 1024,
    }
    try:
        with YoutubeDL(options) as downloader:
            if cookiejar is not None:
                downloader.cookiejar = cookiejar
            info = downloader.extract_info(payload["url"], download=True)
            files = [path for path in output_dir.glob("source.*") if path.suffix not in {".part", ".ytdl", ".json"} and path.stat().st_size > 0]
            if not files or not info:
                raise ValueError("no_media")
            print(json.dumps({"path": str(files[0]), "title": info.get("title") or "视频内容", "video_id": info.get("id"), "uploader": info.get("uploader"), "source_url": info.get("webpage_url") or payload["url"], "cookie_count": cookie_count}, ensure_ascii=False), flush=True)
    except Exception as error:
        message = str(error).lower()
        if "fresh cookies" in message or "login" in message or "sign in" in message:
            code, text = "platform_session_required", "平台未接受当前浏览器会话。请在该浏览器中打开并播放目标视频，再点击重试"
        elif "unsupported url" in message:
            code, text = "unsupported_url", "下载器暂不支持这个链接，请使用该视频的完整网页链接或上传原文件"
        elif "timed out" in message or "timeout" in message:
            code, text = "network_timeout", "连接视频平台超时，请稍后重试"
        else:
            code, text = "download_failed", "未取得原视频：可能是内容不可访问、平台限制或网络错误。请确认该链接可在所选浏览器播放"
        print(json.dumps({"error_code": code, "error": text, "cookie_count": cookie_count}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        run_download(json.loads(sys.stdin.read()))
    except Exception:
        print(json.dumps({"error_code": "download_failed", "error": "视频下载进程异常，未生成摘要"}), flush=True)
