"""文件: main.py；模块: API；功能: 后台执行获取、转写和摘要并公开安全进度；依赖: FastAPI。"""

from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .browser_sessions import discover_profiles
from .models import CreateJobRequest, JobResponse, JobStatus, SourceType
from .services import FasterWhisperTranscriber, FaithfulTextSummarizer, LocalMediaProcessor, MediaPreparationError, PlatformDetector, UrlMediaFetcher

app = FastAPI(title="Video AI 保真内容提取服务", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
_jobs: dict[str, JobResponse] = {}
_summarizer = FaithfulTextSummarizer()
_media_processor = LocalMediaProcessor()
_transcriber = FasterWhisperTranscriber()
_url_fetcher = UrlMediaFetcher()


def update_job(job_id: str, **fields: object) -> None:
    """功能: 原子替换任务进度；job_id 为任务标识，fields 为允许公开的字段；返回无。"""
    _jobs[job_id] = _jobs[job_id].model_copy(update=fields)


def process_media_job(job_id: str, language: str, media_path: Path | None = None, url: str | None = None, browser: str = "auto", title: str = "媒体内容") -> None:
    """功能: 后台处理内容；job_id 为任务标识，language 为语言，media_path/url 为来源，browser 为会话选择，title 为上传名称；返回无。"""
    audio_path = None
    download = None
    try:
        update_job(job_id, status=JobStatus.PROCESSING)
        if url:
            download = _url_fetcher.fetch(url, browser, lambda **fields: update_job(job_id, **fields))
            media_path, title = download.path, download.title
        update_job(job_id, stage="audio", message="正在提取原视频音轨")
        audio_path = _media_processor.prepare_audio(media_path)
        update_job(job_id, stage="transcribe", message="正在本地转写语音，请稍候")
        segments = _transcriber.transcribe(audio_path, language)
        if not segments:
            raise MediaPreparationError("没有识别到语音，无法从音轨生成摘要", "no_speech")
        update_job(job_id, stage="summarize", message="正在从真实转写中提取摘要")
        result = _summarizer.summarize(" ".join(segment.text for segment in segments), title)
        result.segments = segments
        if download:
            result.source_url, result.video_id, result.uploader = download.source_url, download.video_id, download.uploader
        update_job(job_id, status=JobStatus.COMPLETED, stage="completed", message="内容提取完成", result=result)
    except Exception as error:
        known = isinstance(error, (MediaPreparationError, ValueError))
        update_job(job_id, status=JobStatus.FAILED, stage="failed", message="内容提取失败", error=str(error) if known else "处理过程异常，未生成摘要，请重试", error_code=getattr(error, "code", "processing_failed"))
    finally:
        if audio_path:
            audio_path.unlink(missing_ok=True)
        if media_path:
            if download:
                shutil.rmtree(media_path.parent, ignore_errors=True)
            else:
                media_path.unlink(missing_ok=True)


@app.get("/health")
async def health() -> dict[str, str]:
    """功能: 返回存活状态；参数无；返回 ok。"""
    return {"status": "ok"}


@app.get("/api/v1/browser-sessions")
async def browser_sessions(platform: str = "douyin") -> dict:
    """功能: 返回会话元数据；platform 为平台名；返回配置列表和 Cookie 计数，不解密或返回 Cookie 值。"""
    if platform not in PlatformDetector.domains:
        raise HTTPException(status_code=422, detail="未知平台")
    profiles = await run_in_threadpool(discover_profiles, platform)
    return {"platform": platform, "profiles": [profile.public() for profile in profiles], "message": "已发现平台会话；能否解密并下载将在分析时验证" if any(profile.cookie_count for profile in profiles) else "尚未发现有效平台会话，可先在本机浏览器打开目标视频"}


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(request: CreateJobRequest, background_tasks: BackgroundTasks) -> JobResponse:
    """功能: 创建任务；request 为文字或链接请求，background_tasks 调度后台工作；立即返回任务标识。"""
    if request.source_type is SourceType.TEXT:
        if not request.text:
            raise HTTPException(status_code=422, detail="请输入文字内容")
        result = _summarizer.summarize(request.text)
        job = JobResponse(id=str(uuid4()), status=JobStatus.COMPLETED, stage="completed", message="内容提取完成", source_type=SourceType.TEXT, result=result)
    elif request.source_type is SourceType.URL:
        if not request.url:
            raise HTTPException(status_code=422, detail="请输入视频链接")
        job = JobResponse(id=str(uuid4()), status=JobStatus.QUEUED, source_type=SourceType.URL, platform=PlatformDetector.detect(request.url))
        background_tasks.add_task(process_media_job, job.id, request.language, url=request.url, browser=request.browser)
    else:
        raise HTTPException(status_code=422, detail="文件输入请使用 /api/v1/jobs/file")
    _jobs[job.id] = job
    return job


@app.post("/api/v1/jobs/file", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_file_job(background_tasks: BackgroundTasks, file: UploadFile = File(...), language: str = Form("zh")) -> JobResponse:
    """功能: 分块保存上传文件并排队；background_tasks 为调度器，file 为媒体，language 为语言；返回任务。"""
    size = 0
    media_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=Path(file.filename or "media.bin").suffix) as temporary:
            media_path = Path(temporary.name)
            while content := await file.read(1024 * 1024):
                size += len(content)
                if size > 500 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="文件不能超过 500 MB")
                await run_in_threadpool(temporary.write, content)
        if size == 0:
            raise HTTPException(status_code=422, detail="上传文件为空")
    except Exception:
        if media_path:
            media_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    job = JobResponse(id=str(uuid4()), status=JobStatus.QUEUED, source_type=SourceType.FILE)
    _jobs[job.id] = job
    background_tasks.add_task(process_media_job, job.id, language, media_path=media_path, title=file.filename or "媒体内容")
    return job


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """功能: 查询任务；job_id 为任务标识；返回当前进度、结果或 404。"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="任务不存在，服务重启后请重新提交")
    return _jobs[job_id]
