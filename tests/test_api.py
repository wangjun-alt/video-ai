"""文件: test_api.py；模块: 回归测试；功能: 验证分享文案、后台任务、真实错误及来源一致性；依赖: pytest。"""

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

import app.main as main
from app.inputs import extract_source_url
from app.models import TranscriptSegment
from app.services import MediaDownload, MediaPreparationError

client = TestClient(main.app)


def test_health() -> None:
    """功能: 验证健康检查；参数无；返回无。"""
    assert client.get('/health').json() == {'status': 'ok'}


def test_text_job_keeps_source_sentences() -> None:
    """功能: 验证摘要来自提交原文；参数无；返回无。"""
    text = '产品目标是减少人工整理时间。第一步是提取音频。第二步是生成摘要。'
    response = client.post('/api/v1/jobs', json={'source_type': 'text', 'text': text})
    assert response.status_code == 201
    body = response.json()
    assert body['status'] == 'completed'
    assert body['result']['summary'] == text
    assert body['result']['transcript'] == text


def test_share_text_extracts_url_and_rejects_non_http() -> None:
    """功能: 验证完整分享文案及输入校验；参数无；返回无。"""
    assert extract_source_url('复制打开抖音 https://v.douyin.com/58PNrewOrFE/ e@B.GV') == 'https://v.douyin.com/58PNrewOrFE/'
    response = client.post('/api/v1/jobs', json={'source_type': 'url', 'url': 'file:///etc/passwd'})
    assert response.status_code == 422


def test_url_failure_is_queryable_without_fake_result(monkeypatch) -> None:
    """功能: 验证后台会话错误不生成假摘要；monkeypatch 隔离外部平台；返回无。"""
    def fail(*args, **kwargs):
        """功能: 模拟系统会话阻碍；args/kwargs 为下载参数；始终抛出指定错误。"""
        raise MediaPreparationError('请解锁 Mac', 'browser_access_timeout')
    monkeypatch.setattr(main._url_fetcher, 'fetch', fail)
    response = client.post('/api/v1/jobs', json={'source_type': 'url', 'url': 'https://www.bilibili.com/video/BV1xx'})
    assert response.status_code == 201
    assert response.json()['status'] == 'queued'
    job = client.get('/api/v1/jobs/' + response.json()['id']).json()
    assert job['platform'] == 'bilibili'
    assert job['status'] == 'failed'
    assert job['error_code'] == 'browser_access_timeout'
    assert job['result'] is None


def test_url_result_uses_downloaded_source_and_cleans_temp_files(monkeypatch) -> None:
    """功能: 验证下载身份、原文与清理；monkeypatch 注入媒体依赖；返回无。"""
    root = Path(tempfile.mkdtemp(prefix='video-ai-test-'))
    media = root / 'source.mp4'
    media.write_bytes(b'media')
    audio = root / 'source.wav'
    audio.write_bytes(b'audio')
    def fetch(url, browser, update):
        """功能: 返回固定下载身份；url/browser/update 为来源和进度参数；返回测试媒体。"""
        update(browser='chrome', browser_profile='Default', cookie_count=2)
        return MediaDownload(media, '原视频标题', url, 'video-123', '原作者')
    monkeypatch.setattr(main._url_fetcher, 'fetch', fetch)
    monkeypatch.setattr(main._media_processor, 'prepare_audio', lambda path: audio)
    monkeypatch.setattr(main._transcriber, 'transcribe', lambda path, language: [TranscriptSegment(start_seconds=0, end_seconds=2, text='这是原视频的真实转写内容。')])
    response = client.post('/api/v1/jobs', json={'source_type': 'url', 'url': 'https://www.douyin.com/video/123'})
    job = client.get('/api/v1/jobs/' + response.json()['id']).json()
    assert job['status'] == 'completed'
    assert job['result']['title'] == '原视频标题'
    assert job['result']['video_id'] == 'video-123'
    assert job['result']['uploader'] == '原作者'
    assert job['result']['transcript'] == '这是原视频的真实转写内容。'
    assert not root.exists()


def test_invalid_media_reports_actual_error() -> None:
    """功能: 验证非媒体文件返回真实错误；参数无；返回无。"""
    response = client.post('/api/v1/jobs/file', files={'file': ('sample.txt', b'not media', 'text/plain')})
    job = client.get('/api/v1/jobs/' + response.json()['id']).json()
    assert job['status'] == 'failed'
    assert 'ffmpeg' in job['error']
    assert job['result'] is None


def test_browser_endpoint_never_exposes_credentials(monkeypatch) -> None:
    """功能: 验证会话接口只返回概况；monkeypatch 固定发现结果；返回无。"""
    from app.browser_sessions import BrowserProfile
    monkeypatch.setattr(main, 'discover_profiles', lambda platform: [BrowserProfile('chrome', 'Default', Path('/private/profile'), 3)])
    response = client.get('/api/v1/browser-sessions')
    assert response.status_code == 200
    profile = response.json()['profiles'][0]
    assert set(profile) == {'id', 'browser', 'profile', 'cookie_count'}
    assert profile['cookie_count'] == 3
