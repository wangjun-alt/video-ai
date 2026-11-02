"""
文件: test_browser_media.py
模块: 浏览器媒体获取测试
功能: 验证 CDP 辅助函数不会泄露跨域 Cookie，并正确识别媒体元数据。
依赖: pytest、项目内浏览器媒体模块。
"""

from http.cookiejar import Cookie

from app.browser_media import _browser_cookies, _clean_title, _cookie_header, _extract_video_id, _safe_filename_extension


def _cookie(name: str, value: str, domain: str) -> Cookie:
    """
    功能: 构造测试用内存 Cookie。

    参数:
        name (str): Cookie 名称。
        value (str): Cookie 值。
        domain (str): Cookie 所属域名。

    返回:
        Cookie: 标准库 Cookie 对象。
    """
    return Cookie(0, name, value, None, False, domain, domain.startswith("."), domain.startswith("."), "/", True, False, None, False, None, {}, False)


def test_browser_cookie_mapping_and_domain_filter() -> None:
    """功能: 验证浏览器 Cookie 映射仅向匹配的媒体域名发送。"""
    cookies = _browser_cookies([_cookie("session", "secret", ".douyin.com"), _cookie("other", "nope", ".example.com")])
    assert _cookie_header(cookies, "https://v.douyin.com/video.mp4") == "session=secret"


def test_browser_media_metadata_helpers() -> None:
    """功能: 验证标题、视频 ID 和媒体扩展名提取。"""
    assert _clean_title("AI Agent - 抖音") == "AI Agent"
    assert _extract_video_id("https://www.douyin.com/video/7687561602991754536") == "7687561602991754536"
    assert _safe_filename_extension("video/mp4", "https://cdn.example/video") == ".mp4"

