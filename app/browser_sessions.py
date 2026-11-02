"""文件: browser_sessions.py；模块: 本机会话发现；功能: 选择目标平台的浏览器配置，仅公开计数；依赖: SQLite。"""

import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .inputs import PlatformDetector


@dataclass(frozen=True)
class BrowserProfile:
    """浏览器配置的元数据，不保存或返回任何 Cookie 值。"""

    browser: str
    profile: str
    path: Path
    cookie_count: int

    @property
    def id(self) -> str:
        """功能: 生成前端可选标识；参数无；返回浏览器名与配置名。"""
        return f"{self.browser}:{self.profile}"

    def public(self) -> dict[str, str | int]:
        """功能: 输出安全的会话概况；参数无；返回标识、名称及未过期 Cookie 数。"""
        return {"id": self.id, "browser": self.browser, "profile": self.profile, "cookie_count": self.cookie_count}


def browser_roots() -> dict[str, Path]:
    """功能: 获取当前系统的浏览器目录；参数无；返回浏览器与路径映射。"""
    if sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
        return {"chrome": root / "Google/Chrome", "edge": root / "Microsoft Edge", "brave": root / "BraveSoftware/Brave-Browser", "firefox": root / "Firefox/Profiles"}
    if sys.platform == "win32":
        root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return {"chrome": root / "Google/Chrome/User Data", "edge": root / "Microsoft/Edge/User Data", "brave": root / "BraveSoftware/Brave-Browser/User Data", "firefox": Path(os.getenv("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Mozilla/Firefox/Profiles"}
    root = Path.home() / ".config"
    return {"chrome": root / "google-chrome", "chromium": root / "chromium", "edge": root / "microsoft-edge", "brave": root / "BraveSoftware/Brave-Browser", "firefox": Path.home() / ".mozilla/firefox"}


def count_platform_cookies(database: Path, platform: str, firefox: bool = False) -> int:
    """功能: 只统计平台有效 Cookie；database 为数据库，platform 为平台，firefox 指定表结构；返回计数。"""
    domains = PlatformDetector.domains.get(platform, ())
    if not domains or not database.is_file():
        return 0
    table, host, expiry = ("moz_cookies", "host", "expiry") if firefox else ("cookies", "host_key", "expires_utc")
    conditions = " OR ".join(f"({host} = ? OR {host} = ? OR {host} LIKE ?)" for _ in domains)
    parameters = [item for domain in domains for item in (domain, f".{domain}", f"%.{domain}")]
    try:
        with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=1) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0] if firefox else 0
            now = int(time.time() * (1000 if version >= 16 else 1)) if firefox else int((time.time() + 11644473600) * 1_000_000)
            return connection.execute(f"SELECT COUNT(*) FROM {table} WHERE ({conditions}) AND ({expiry} IS NULL OR {expiry} = 0 OR {expiry} > ?)", (*parameters, now)).fetchone()[0]
    except sqlite3.Error:
        return 0


def discover_profiles(platform: str) -> list[BrowserProfile]:
    """功能: 发现本机配置；platform 为目标平台；返回按平台 Cookie 数排序的配置列表，不读取密文值。"""
    profiles = []
    for browser, root in browser_roots().items():
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if browser == "firefox":
                database = child / "cookies.sqlite"
            elif child.name == "Default" or child.name.startswith("Profile "):
                database = next((path for path in (child / "Network/Cookies", child / "Cookies") if path.is_file()), child / "Cookies")
            else:
                continue
            if database.is_file():
                profiles.append(BrowserProfile(browser, child.name, child, count_platform_cookies(database, platform, browser == "firefox")))
    return sorted(profiles, key=lambda item: -item.cookie_count)


def select_profiles(platform: str, selection: str = "auto") -> list[BrowserProfile]:
    """功能: 选择配置；platform 为目标平台，selection 为 auto/off 或已发现标识；返回可尝试配置。"""
    selection = os.getenv("VIDEO_AI_BROWSER", "auto") if selection == "auto" else selection
    if selection in {"off", "none"} or platform == "generic":
        return []
    profiles = discover_profiles(platform)
    if selection == "auto":
        return [profile for profile in profiles if profile.cookie_count > 0]
    matching = [profile for profile in profiles if selection in {profile.id, profile.browser}]
    if not matching:
        raise ValueError("所选浏览器配置不存在，请刷新浏览器会话列表")
    return matching
