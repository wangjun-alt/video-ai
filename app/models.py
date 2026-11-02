"""
文件: app/models.py
模块: 数据模型
功能: 定义输入请求、任务状态和摘要输出的扁平数据结构。
依赖: pydantic
"""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from .inputs import extract_source_url


class SourceType(StrEnum):
    """输入来源类型。"""

    URL = "url"
    FILE = "file"
    TEXT = "text"


class JobStatus(StrEnum):
    """任务生命周期状态。"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateJobRequest(BaseModel):
    """文字或链接任务请求。"""

    source_type: SourceType
    url: str | None = Field(default=None, max_length=8192)
    text: str | None = Field(default=None, max_length=2_000_000)
    language: str = Field(default="zh", min_length=2, max_length=16)
    summary_style: str = Field(default="faithful", min_length=2, max_length=32)
    browser: str = Field(default="auto", max_length=128)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        """功能: 清理链接字段；参数为用户提交的 URL；返回规范化后的 URL。"""
        return extract_source_url(value.strip()) if value else value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        """功能: 清理文字字段；参数为用户提交的文本；返回去除首尾空白的文本。"""
        return value.strip() if value else value


class TranscriptSegment(BaseModel):
    """带时间范围的转写片段。"""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)


class SummaryResult(BaseModel):
    """保真摘要结果，包含可回溯证据和处理提示。"""

    title: str
    summary: str
    key_points: list[str]
    source_excerpt: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    transcript: str = ""
    source_url: str | None = None
    video_id: str | None = None
    uploader: str | None = None


class JobResponse(BaseModel):
    """任务状态响应。"""

    id: str
    status: JobStatus
    source_type: SourceType
    platform: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    result: SummaryResult | None = None
    error: str | None = None
    error_code: str | None = None
    stage: str = "queued"
    message: str = "等待处理"
    browser: str | None = None
    browser_profile: str | None = None
    cookie_count: int = 0
