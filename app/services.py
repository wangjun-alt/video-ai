"""
文件: app/services.py
模块: 内容处理服务
功能: 提供平台识别、文字保真摘要、媒体文件检查和可插拔接口。
依赖: Python 标准库、Pydantic 数据模型
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import os
import json
import signal
import sys
import time
from dataclasses import dataclass
from threading import Lock
from pathlib import Path
from typing import Callable, Protocol

from .browser_sessions import select_profiles
from .inputs import PlatformDetector
from .models import SummaryResult, TranscriptSegment


class Transcriber(Protocol):
    """语音转写器协议，便于替换 faster-whisper 或云端 ASR。"""

    def transcribe(self, media_path: Path, language: str) -> list[TranscriptSegment]:
        """功能: 将媒体转为带时间戳的文本片段。"""


class FaithfulTextSummarizer:
    """基于句子抽取的离线摘要器，保证每个要点来自原文。"""

    _splitter = re.compile(r"(?<=[。！？!?；;\n])\s*")

    def summarize(self, text: str, title: str = "文字内容") -> SummaryResult:
        """功能: 从原文抽取高信息密度句子生成保真摘要。

        参数:
            text (str): 已完成转写或用户输入的原文。
            title (str): 摘要标题，默认使用通用标题。
        返回:
            SummaryResult: 包含摘要、要点和原文证据的结果。
        """
        normalized = " ".join(text.split())
        sentences = [item.strip() for item in self._splitter.split(normalized) if item.strip()]
        if not sentences:
            raise ValueError("文本内容为空，无法生成摘要")
        truncated = False
        if len(sentences) <= 6:
            selected = sentences
        else:
            # 抽取首句、末句和包含高频主题词的句子，避免改写原意。
            frequencies: dict[str, int] = {}
            for sentence in sentences:
                for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", sentence.lower()):
                    frequencies[word] = frequencies.get(word, 0) + 1
            scored = sorted(
                enumerate(sentences),
                key=lambda pair: sum(frequencies.get(word, 0) for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", pair[1].lower())),
                reverse=True,
            )
            chosen = {0, len(sentences) - 1, *(index for index, _ in scored[:2])}
            selected = [sentence for index, sentence in enumerate(sentences) if index in chosen]
            truncated = len(selected) < len(sentences)
        summary = "".join(selected)
        key_points = selected[: min(5, len(selected))]
        warnings = ["当前使用离线抽取式摘要；接入大模型后仍应保留原文引用并人工抽查。"]
        if truncated:
            warnings.append("原文较长，离线摘要只抽取部分句子；不要将其当作最终事实依据。")
        return SummaryResult(
            title=title,
            summary=summary,
            key_points=key_points,
            source_excerpt=normalized[:1000],
            warnings=warnings,
            transcript=normalized,
        )


class MediaPreparationError(RuntimeError):
    """媒体准备失败时返回给 API 层的可读错误。"""

    def __init__(self, message: str, code: str = "media_failed") -> None:
        """功能: 保存可读原因和错误码；message 为用户提示，code 为机器可读原因；返回无。"""
        super().__init__(message)
        self.code = code


@dataclass
class MediaDownload:
    """下载结果与真实来源元数据，不包含浏览器凭据。"""

    path: Path
    title: str
    source_url: str
    video_id: str | None = None
    uploader: str | None = None


class UrlMediaFetcher:
    """隔离浏览器解密和下载，自动按目标平台会话选择配置，并限制等待时间。"""

    def fetch(self, url: str, browser: str = "auto", update: Callable[..., None] | None = None) -> MediaDownload:
        """功能: 获取原媒体；url 为规范链接，browser 为配置选择，update 接收安全进度；返回媒体及来源。"""
        platform = PlatformDetector.detect(url)
        profiles = select_profiles(platform, browser)
        candidates = profiles[:3] or [None]
        for index, profile in enumerate(candidates):
            output_dir = Path(tempfile.mkdtemp(prefix="video-ai-download-"))
            payload = {"url": url, "output_dir": str(output_dir), "browser_automation": browser not in {"off", "none"}}
            if profile:
                payload.update(browser=profile.browser, profile=profile.profile, profile_path=str(profile.path))
            if update:
                update(stage="browser" if profile else "download", message="自动选择浏览器会话" if profile else "正在获取原视频", browser=profile.browser if profile else None, browser_profile=profile.profile if profile else None, cookie_count=0)
            try:
                result = self._run_worker(payload, update)
                if result.get("error"):
                    raise MediaPreparationError(result["error"], result["error_code"])
                return MediaDownload(path=Path(result["path"]), title=result["title"], source_url=result["source_url"], video_id=result.get("video_id"), uploader=result.get("uploader"))
            except MediaPreparationError as error:
                shutil.rmtree(output_dir, ignore_errors=True)
                if error.code not in {"platform_session_required", "browser_session_empty", "browser_access_failed"} or index == len(candidates) - 1:
                    raise
            except Exception:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
        raise MediaPreparationError("没有可用的平台会话")

    def _run_worker(self, payload: dict, update: Callable[..., None] | None) -> dict:
        """功能: 监控隔离进程；payload 为下载参数，update 为进度回调；返回非敏感结果或超时错误。"""
        progress_path = Path(payload["output_dir"]) / "progress.json"
        with tempfile.TemporaryFile(mode="w+") as output:
            process = subprocess.Popen([sys.executable, "-m", "app.download_worker"], stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL, text=True, start_new_session=True, cwd=Path(__file__).resolve().parent.parent)
            try:
                process.stdin.write(json.dumps(payload))
                process.stdin.close()
                started = time.monotonic()
                last_stage = "browser" if payload.get("browser") else "download"
                last_progress = None
                while process.poll() is None:
                    if progress_path.exists():
                        try:
                            progress = json.loads(progress_path.read_text(encoding="utf-8"))
                        except (ValueError, OSError):
                            progress = {}
                        if progress and progress != last_progress:
                            if progress["stage"] != last_stage:
                                started = time.monotonic()
                                last_stage = progress["stage"]
                            if update:
                                update(**progress)
                            last_progress = progress
                    timeout = 120 if last_stage in {"browser", "browser_media"} else 240
                    if time.monotonic() - started > timeout:
                        if last_stage in {"browser", "browser_media"}:
                            raise MediaPreparationError("读取浏览器会话超时。请解锁 Mac，并在出现 Chrome Safe Storage 钥匙串提示时完成授权，然后点击重试", "browser_access_timeout")
                        raise MediaPreparationError("获取原视频超时，请确认网络及链接可正常播放后重试", "download_timeout")
                    time.sleep(0.25)
                output.seek(0)
                lines = output.read().strip().splitlines()
                if not lines:
                    raise MediaPreparationError("视频下载进程未返回结果", "download_failed")
                result = json.loads(lines[-1])
                if update and "cookie_count" in result:
                    update(cookie_count=result["cookie_count"])
                return result
            finally:
                # 结束整组子进程，避免系统钥匙串进程在超时后继续等待。
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()


class LocalMediaProcessor:
    """检查本地媒体并预留 FFmpeg/ASR 处理入口。"""

    def prepare_audio(self, media_path: Path) -> Path:
        """功能: 将视频或音频准备成 WAV；参数为本地媒体路径；返回临时音频路径。"""
        if not media_path.exists():
            raise MediaPreparationError("上传文件不存在")
        if shutil.which("ffmpeg") is None:
            raise MediaPreparationError("处理音视频需要安装 ffmpeg；文字输入无需安装此依赖")
        descriptor, name = tempfile.mkstemp(suffix=".wav")
        os.close(descriptor)
        output = Path(name)
        command = ["ffmpeg", "-y", "-i", str(media_path), "-ar", "16000", "-ac", "1", str(output)]
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
        except subprocess.TimeoutExpired as error:
            output.unlink(missing_ok=True)
            raise MediaPreparationError("提取音轨超时", "audio_timeout") from error
        if process.returncode != 0:
            output.unlink(missing_ok=True)
            raise MediaPreparationError(f"ffmpeg 无法读取媒体：{process.stderr[-500:]}")
        return output


class FasterWhisperTranscriber:
    """基于 faster-whisper 的可选本地转写器。"""

    def __init__(self, model_size: str = "small") -> None:
        """功能: 延迟加载语音模型；参数为模型大小，如 tiny、small 或 medium。"""
        self.model_size = os.getenv("VIDEO_AI_WHISPER_MODEL", model_size)
        self._model = None
        self._lock = Lock()

    def transcribe(self, media_path: Path, language: str) -> list[TranscriptSegment]:
        """功能: 将音频转成带时间戳片段；参数为音频路径和语言代码；返回片段列表。"""
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise MediaPreparationError("未安装 faster-whisper，请执行 pip install -e '.[media]'") from error
        with self._lock:
            try:
                if self._model is None:
                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8", local_files_only=True)
                segments, _ = self._model.transcribe(str(media_path), language=language, vad_filter=True)
                return [TranscriptSegment(start_seconds=segment.start, end_seconds=segment.end, text=segment.text.strip()) for segment in segments if segment.text.strip()]
            except Exception as error:
                raise MediaPreparationError("本地语音模型尚未就绪或转写失败，请检查模型配置", "transcription_failed") from error
