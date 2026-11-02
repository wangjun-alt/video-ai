# Video AI 内容提取工作台

文件: README.md  
模块: 项目说明  
功能: 说明 React 工作台、自动浏览器会话、媒体转写和原文摘要的运行方式。

## 使用

打开 [工作台](http://127.0.0.1:5173/)，粘贴抖音、B站、小红书链接或整段分享文案，保留“自动获取（推荐）”，点击“开始分析”。也可上传音视频文件或粘贴文字。界面使用 React 与 shadcn/ui，显示实际后台阶段、准确失败原因，以及完成后的标题、作者、视频 ID、摘要和带时间戳的完整转写。

浏览器发现支持 Chrome、Edge、Brave、Firefox 配置。自动选择存在未过期目标平台 Cookie 的配置；也可以手动选已发现配置或关闭会话读取。这里只使用本地服务机器的浏览器，不能读取另一台电脑浏览器中的会话。

macOS 使用系统钥匙串解密 Chromium 会话。请保持 Mac 已解锁；首次读取时，若系统显示 Chrome Safe Storage 等提示，在本机完成授权。检测到 Cookie 不代表系统允许解密，也不代表平台接受会话；读取超时或平台拒绝时页面会显示原因，可直接重试，无需手动导出 Cookie。

## 启动本地服务

需要 Python 3.11+、Node.js 22+ 和 FFmpeg。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[media,test]'
brew install ffmpeg
```

启动前缓存本地语音模型。默认模型是 Systran/faster-whisper-small，CPU 使用 int8。首次缓存需要网络；处理任务时只加载已缓存模型。

```bash
python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('Systran/faster-whisper-small', allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'])
PY
```

若官方模型站连接超时，可在上述命令前设置 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`。`VIDEO_AI_WHISPER_MODEL` 可指定其他已缓存模型或本地模型目录。

一个终端运行后端：

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

另一个终端运行前端：

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

前端默认使用 Vite 同源代理访问 8765，避免让页面用户手动填写后端地址。需要独立 API 时可设置 `VITE_API_URL`。API 文档在 [8765/docs](http://127.0.0.1:8765/docs)，后端根路径不是工作台。`npm run build` 生成前端构建产物；`npm run preview` 本身不提供后端代理。

## 处理链与会话范围

1. 分享文案提取有效 HTTP 链接，按域名识别平台。
2. 浏览器发现只统计会话，不返回 Cookie 值或本机路径。
3. 独立工作进程将目标平台未过期会话读取到内存，再启动临时隔离 Chrome；不复制整个浏览器 Cookie 数据库到临时文件，不保存 Cookie 导出文件。只在访问对应平台时发送其 Cookie，页面与转写/摘要器不接收这些凭据。
4. 隔离 Chrome 打开原始页面并监听真实媒体请求。抖音等平台可能把视频和音频分开下发，系统优先保存音频轨，避免拿到无声的视频轨；浏览器媒体获取失败时回退到 yt-dlp。
5. FFmpeg 提取音轨，faster-whisper 在本地转写语音；抽取式摘要选择原文句子，返回完整原文和时间片段，不为下载失败的链接生成摘要。

浏览器会话读取和隔离浏览器媒体阶段最多等待 120 秒，下载器回退阶段最多等待 240 秒。超时会结束整组工作子进程，防止钥匙串进程持续等待。失败自动清理下载文件；处理完成后清理临时媒体和音轨。任务通过后台线程执行，下载/转写期间健康检查和查询接口仍可响应。

## API 示例

文字提交直接完成：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"text","text":"目标是减少人工整理时间。第一步提取音频。第二步生成摘要。"}'
```

链接或上传返回任务 ID，随后轮询任务状态：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"url","url":"https://v.douyin.com/你的分享标识/","browser":"auto","language":"zh"}'

curl -X POST http://127.0.0.1:8765/api/v1/jobs/file \
  -F 'file=@demo.mp4' -F 'language=zh'

curl http://127.0.0.1:8765/api/v1/jobs/返回的任务ID
```

状态为 queued、processing、completed 或 failed。`stage`、`message` 展示实际进度，失败返回 `error_code` 和 `error`，只有完成才有 `result`。

## 当前能力和限制

- 已接入实际 FFmpeg 与 faster-whisper，以及纯文字抽取式摘要。摘要没有经过人工评测，不提供虚构的保真度分数；语音识别可能有误，数字、名称和条件需要结合原文核对。
- 本版本处理音轨语音，不识别画面内文字、图表或纯无声视频。
- 平台能否下载取决于链接可访问性、会话有效性及 yt-dlp 的平台支持。自动 Cookie 读取不能保证所有抖音/B站/小红书链接成功。
- 任务保存在进程内存中，重启后需重新提交；上传上限 500 MB。本地开发版本尚无用户鉴权或持久化任务队列，请绑定 127.0.0.1 使用。
- 会话适配器使用 yt-dlp 的数据库读取接口，升级下载器时应运行会话范围测试。

## 验证

```bash
python3 -m pytest -q
cd frontend
npm run build
```

回归测试覆盖分享文案、来源身份与原文一致、后台失败不生成假摘要、临时文件清理，以及真实下载器读取合成 Firefox 会话时的平台范围和过期过滤。真实平台下载需另用可播放的实际链接验证；构建通过不等于平台解析通过。
