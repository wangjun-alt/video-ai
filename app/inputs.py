"""文件: inputs.py；模块: 输入解析；功能: 从平台分享文案中提取并校验链接；依赖: 标准库。"""

import re
from urllib.parse import urlparse


class PlatformDetector:
    """通过域名识别平台，同时提供浏览器会话的允许域名范围。"""

    domains = {
        "douyin": ("douyin.com", "iesdouyin.com"),
        "bilibili": ("bilibili.com", "b23.tv"),
        "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    }

    @classmethod
    def detect(cls, url: str) -> str:
        """功能: 识别链接平台；url 为完整 HTTP 链接；返回平台名或 generic。"""
        hostname = (urlparse(url).hostname or "").lower()
        for platform, domains in cls.domains.items():
            if any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains):
                return platform
        return "generic"


def extract_source_url(value: str) -> str:
    """功能: 提取分享链接；value 为链接或完整分享文案；返回首个支持的平台链接或单个 HTTP 链接。"""
    urls = [match.rstrip("。，！、；：）】》,.!?;:)") for match in re.findall(r"https?://[^\s<>\"'\\]+", value)]
    if not urls:
        raise ValueError("请粘贴有效的 http/https 视频链接，或包含链接的分享文案")
    supported = [url for url in urls if PlatformDetector.detect(url) != "generic"]
    url = (supported or urls)[0]
    parsed = urlparse(url)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("视频链接格式不正确")
    return url
