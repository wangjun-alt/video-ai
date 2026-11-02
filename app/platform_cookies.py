"""文件: platform_cookies.py；模块: 平台会话适配；功能: 仅在内存读取目标平台 Cookie，再交给下载器解密；依赖: yt-dlp、SQLite。"""

import sqlite3
import time
from pathlib import Path

from .inputs import PlatformDetector


def open_platform_database(database_path: str, platform: str) -> sqlite3.Cursor:
    """功能: 创建只含目标平台会话的内存数据库；database_path 为浏览器数据库，platform 为目标平台；返回由调用方关闭的游标。"""
    domains = PlatformDetector.domains.get(platform, ())
    if not domains:
        raise ValueError("未知平台，不能读取浏览器会话")
    memory = sqlite3.connect(":memory:")
    try:
        with sqlite3.connect(f"{Path(database_path).resolve().as_uri()}?mode=ro", uri=True, timeout=2) as source:
            version = source.execute("PRAGMA user_version").fetchone()[0]
            memory.execute(f"PRAGMA user_version = {version}")
            firefox = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='moz_cookies'").fetchone() is not None
            table, host, expiry = ("moz_cookies", "host", "expiry") if firefox else ("cookies", "host_key", "expires_utc")
            memory.execute(source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0])
            now = int(time.time() * (1000 if version >= 16 else 1)) if firefox else int((time.time() + 11644473600) * 1_000_000)
            conditions = " OR ".join(f"({host} = ? OR {host} = ? OR {host} LIKE ?)" for _ in domains)
            parameters = [item for domain in domains for item in (domain, f".{domain}", f"%.{domain}")]
            selected = source.execute(f"SELECT * FROM {table} WHERE ({conditions}) AND ({expiry} IS NULL OR {expiry} = 0 OR {expiry} > ?)", (*parameters, now))
            placeholders = ",".join("?" for _ in selected.description)
            memory.executemany(f"INSERT INTO {table} VALUES ({placeholders})", selected)
            if not firefox:
                memory.execute(source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()[0])
                metadata = source.execute("SELECT * FROM meta")
                memory.executemany("INSERT INTO meta VALUES (" + ",".join("?" for _ in metadata.description) + ")", metadata)
        return memory.cursor()
    except Exception:
        memory.close()
        raise


def extract_platform_cookies(browser: str, profile_path: str, platform: str, logger):
    """功能: 在隔离下载进程读取目标会话；browser 为浏览器名，profile_path 为已发现路径，platform 为平台，logger 为安全日志；返回内存 Cookie 容器。"""
    import yt_dlp.cookies as cookies

    original = cookies._open_database_copy

    def open_filtered(database_path, temporary_directory):
        """功能: 替换下载器数据库副本；database_path 为来源，temporary_directory 为上游临时目录且不使用；返回平台内存游标。"""
        return open_platform_database(database_path, platform)

    # 适配只在独立工作进程内生效，保留上游浏览器解密和系统钥匙串逻辑。
    cookies._open_database_copy = open_filtered
    try:
        jar = cookies.extract_cookies_from_browser(browser, profile=profile_path, logger=logger)
        for cookie in jar:
            if cookie.expires == 0:
                cookie.expires = None
        return jar
    finally:
        cookies._open_database_copy = original
