"""文件: test_browser_sessions.py；模块: 会话测试；功能: 验证读取范围、过期过滤和 Firefox 毫秒时间；依赖: pytest、SQLite、yt-dlp。"""

import sqlite3
import time

from app.browser_sessions import count_platform_cookies
from app.download_worker import QuietLogger
from app.platform_cookies import extract_platform_cookies, open_platform_database


def test_firefox_session_reads_only_valid_target_domains(tmp_path):
    """功能: 通过真实下载器读取合成会话数据库；tmp_path 为隔离配置目录；返回无，确认不读取无关或过期会话。"""
    database = tmp_path / "cookies.sqlite"
    now = int(time.time() * 1000)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=16")
        connection.execute("CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT, path TEXT, expiry INTEGER, isSecure INTEGER)")
        connection.executemany("INSERT INTO moz_cookies VALUES (?, ?, ?, '/', ?, 1)", [
            (".douyin.com", "valid", "synthetic-test", now + 60000),
            ("www.douyin.com", "session", "synthetic-test", 0),
            (".douyin.com", "expired", "synthetic-test", now - 60000),
            ("unrelated.example", "other", "synthetic-test", now + 60000),
            ("douyin.com.unrelated.example", "wrong_suffix", "synthetic-test", now + 60000),
        ])
    assert count_platform_cookies(database, "douyin", firefox=True) == 2
    cursor = open_platform_database(str(database), "douyin")
    try:
        assert cursor.execute("PRAGMA database_list").fetchone()[2] == ""
        assert cursor.execute("SELECT COUNT(*) FROM moz_cookies").fetchone()[0] == 2
    finally:
        cursor.connection.close()
    jar = extract_platform_cookies("firefox", str(tmp_path), "douyin", QuietLogger())
    assert {cookie.name for cookie in jar} == {"valid", "session"}
    assert list(tmp_path.iterdir()) == [database]


def test_chromium_database_scope_and_metadata(tmp_path):
    """功能: 验证 Chromium 解密前已按平台过滤；tmp_path 为合成数据库目录；返回无，保留解密版本元数据。"""
    database = tmp_path / "Cookies"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        connection.execute("INSERT INTO meta VALUES ('version', '24')")
        connection.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, path TEXT, expires_utc INTEGER, is_secure INTEGER)")
        connection.executemany("INSERT INTO cookies VALUES (?, 'test', '', X'', '/', 0, 1)", [(".douyin.com",), (".bilibili.com",)])
    cursor = open_platform_database(str(database), "douyin")
    try:
        assert cursor.execute("SELECT host_key FROM cookies").fetchall() == [(".douyin.com",)]
        assert cursor.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0] == "24"
    finally:
        cursor.connection.close()
