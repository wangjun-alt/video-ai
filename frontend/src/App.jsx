/** 文件: App.jsx；模块: 内容工作台；功能: 使用 React 和 shadcn 提交来源并展示真实进度及原文；依赖: 本地 API。 */
import React, { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, Clipboard, FileText, Link2, LoaderCircle, Mic2, RefreshCw, ShieldCheck, Sparkles, Upload, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Field, FieldGroup, FieldLabel, FieldDescription } from "@/components/ui/field";
import { InputGroup, InputGroupInput, InputGroupAddon, InputGroupButton } from "@/components/ui/input-group";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from "@/components/ui/select";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { API_URL, requestJson } from "@/lib/api";

const ACTIVE = new Set(["queued", "processing"]);

/** 功能: 判断分享文本平台；value 为链接或分享文案；返回会话发现的目标平台。 */
function sourcePlatform(value) {
  if (/bilibili\.com|b23\.tv/i.test(value)) return "bilibili";
  if (/xiaohongshu\.com|xhslink\.com/i.test(value)) return "xiaohongshu";
  return "douyin";
}

/** 功能: 工作台主组件；参数无；返回输入、会话选择、进度和结果视图。 */
export default function App() {
  const [mode, setMode] = useState("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [language, setLanguage] = useState("zh");
  const [browserChoice, setBrowserChoice] = useState("auto");
  const [sessions, setSessions] = useState(null);
  const [connection, setConnection] = useState("checking");
  const [job, setJob] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const fileInput = useRef(null);
  const platform = sourcePlatform(url);
  const busy = submitting || ACTIVE.has(job?.status);
  const canSubmit = mode === "url" ? Boolean(url.trim()) : mode === "text" ? Boolean(text.trim()) : Boolean(file);
  const result = job?.status === "completed" ? job.result : null;

  // 定期实际检查服务；卸载时取消请求，避免重复的健康检查。
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    /** 功能: 检查服务状态；参数无；安排下一次检查。 */
    async function checkHealth() {
      try {
        await requestJson("/health", { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) });
        if (!controller.signal.aborted) setConnection("connected");
      } catch {
        if (!controller.signal.aborted) setConnection("disconnected");
      }
      if (!controller.signal.aborted) timer = setTimeout(checkHealth, 10000);
    }
    checkHealth();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  // 平台变更后只发现配置元数据；点击分析时才读取会话。
  useEffect(() => {
    const controller = new AbortController();
    setSessions(null);
    requestJson(`/api/v1/browser-sessions?platform=${platform}`, { signal: controller.signal })
      .then((body) => { if (!controller.signal.aborted) setSessions(body); })
      .catch(() => { if (!controller.signal.aborted) setSessions({ profiles: [], message: "浏览器会话暂不可检测，请刷新重试" }); });
    return () => controller.abort();
  }, [platform]);

  // 单次轮询完成后再调度下一次；耗时下载不会阻塞页面或服务健康检查。
  useEffect(() => {
    if (!ACTIVE.has(job?.status)) return;
    const controller = new AbortController();
    let timer;
    /** 功能: 查询任务进度；参数无；更新真实状态或连接错误。 */
    async function poll() {
      try {
        const body = await requestJson(`/api/v1/jobs/${job.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJob(body);
        setError(body.error || "");
        if (ACTIVE.has(body.status)) timer = setTimeout(poll, 1000);
      } catch (failure) {
        if (controller.signal.aborted) return;
        setError(failure.message);
        if (failure.status === 404) {
          setJob((current) => ({ ...current, status: "failed", error: failure.message }));
          return;
        }
        timer = setTimeout(poll, 3000);
      }
    }
    timer = setTimeout(poll, 500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job?.id, job?.status]);

  /** 功能: 刷新配置概况；参数无；更新当前平台配置，不解密 Cookie。 */
  async function refreshSessions() {
    setRefreshing(true);
    try { setSessions(await requestJson(`/api/v1/browser-sessions?platform=${platform}`)); }
    catch (failure) { setError(failure.message); }
    finally { setRefreshing(false); }
  }

  /** 功能: 提交来源；event 为表单事件；返回无，后续结果由任务轮询接收。 */
  async function submitJob(event) {
    event.preventDefault();
    if (!canSubmit || busy) return;
    setSubmitting(true); setError(""); setJob(null);
    try {
      let payload;
      if (mode === "file") {
        const body = new FormData(); body.append("file", file); body.append("language", language);
        payload = await requestJson("/api/v1/jobs/file", { method: "POST", body, signal: AbortSignal.timeout(120000) });
      } else {
        payload = await requestJson("/api/v1/jobs", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(mode === "url" ? { source_type: "url", url, language, browser: browserChoice } : { source_type: "text", text, language }),
        });
      }
      setJob(payload); setError(payload.error || "");
    } catch (failure) { setError(failure.message); }
    finally { setSubmitting(false); }
  }

  /** 功能: 粘贴完整分享文案；参数无；更新输入，权限不足时展示手动粘贴提示。 */
  async function pasteLink() {
    try { setUrl(await navigator.clipboard.readText()); setError(""); }
    catch { setError("请直接粘贴到输入框，浏览器暂未允许读取剪贴板"); }
  }

  /** 功能: 选择上传文件；next 为所选文件；检查大小并更新输入。 */
  function chooseFile(next) {
    if (!next) return;
    if (next.size > 500 * 1024 * 1024) { setError("文件不能超过 500 MB"); return; }
    setFile(next); setError("");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand-lockup" href="#workspace"><span className="brand-mark"><Sparkles size={18} /></span><span><strong>Video AI</strong><small>内容提取工作台</small></span></a>
        <nav aria-label="主导航"><a href="#workspace">工作台</a><a href="#results">摘要结果</a></nav>
        <Badge variant="outline">{connection === "connected" ? "本地服务已连接" : connection === "checking" ? "正在连接服务" : "本地服务未连接"}</Badge>
      </header>
      <main id="workspace" className="workspace">
        <section className="intro-row"><p className="eyebrow">保持原意 · 保留原文</p><h1>粘贴链接，<em>让内容变得清晰。</em></h1><p className="intro-copy">视频、音频或文字，一处提取和整理。自动使用本机浏览器会话，摘要与转写原文一起呈现。</p></section>
        <div className="workspace-grid">
          <Card>
            <CardHeader><CardTitle>添加内容</CardTitle><CardDescription>可直接粘贴抖音的整段分享文案，无需先提取网址。</CardDescription></CardHeader>
            <form onSubmit={submitJob}>
              <CardContent className="flex flex-col gap-6">
                <Tabs value={mode} onValueChange={setMode}>
                  <TabsList className="w-full"><TabsTrigger value="url" className="flex-1 gap-2"><Link2 size={16} />视频链接</TabsTrigger><TabsTrigger value="file" className="flex-1 gap-2"><Upload size={16} />上传文件</TabsTrigger><TabsTrigger value="text" className="flex-1 gap-2"><FileText size={16} />粘贴文字</TabsTrigger></TabsList>
                  <TabsContent value="url" className="mt-6">
                    <FieldGroup>
                      <Field data-invalid={Boolean(error)}><FieldLabel htmlFor="url-input">视频链接或分享文案</FieldLabel>
                        <InputGroup className="min-h-12"><InputGroupInput id="url-input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="粘贴抖音、B站或小红书分享内容" aria-invalid={Boolean(error)} /><InputGroupAddon><Link2 /></InputGroupAddon><InputGroupAddon align="inline-end"><InputGroupButton onClick={pasteLink}><Clipboard data-icon="inline-start" />粘贴</InputGroupButton></InputGroupAddon></InputGroup>
                        <FieldDescription>默认自动选择含有对应平台会话的浏览器配置。</FieldDescription>
                      </Field>
                      <Field><FieldLabel htmlFor="browser-choice">浏览器会话</FieldLabel><Select value={browserChoice} onValueChange={setBrowserChoice} disabled={busy}><SelectTrigger id="browser-choice"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="auto">自动获取（推荐）</SelectItem>{(sessions?.profiles || []).map((profile) => <SelectItem key={profile.id} value={profile.id}>{profile.browser} · {profile.profile} · {profile.cookie_count} 条平台 Cookie</SelectItem>)}<SelectItem value="off">不读取浏览器会话</SelectItem></SelectGroup></SelectContent></Select>
                        <div className="flex items-start justify-between gap-3"><FieldDescription>{sessions?.message || "正在检测本机浏览器配置…"}</FieldDescription><Button type="button" variant="ghost" size="sm" onClick={refreshSessions} disabled={refreshing}><RefreshCw data-icon="inline-start" className={refreshing ? "spin" : undefined} />刷新</Button></div>
                      </Field>
                    </FieldGroup>
                  </TabsContent>
                  <TabsContent value="file" className="mt-6"><Field><FieldLabel htmlFor="file-input">上传音视频</FieldLabel><Button type="button" variant="outline" className="min-h-28 w-full flex-col gap-3" onClick={() => fileInput.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]); }}><Upload data-icon="inline-start" />{file ? file.name : "拖入文件，或点击选择"}</Button><input id="file-input" ref={fileInput} type="file" accept="video/*,audio/*" hidden onChange={(event) => chooseFile(event.target.files?.[0])} /><FieldDescription>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "支持 MP4、MOV、MP3、WAV，最大 500 MB"}</FieldDescription></Field></TabsContent>
                  <TabsContent value="text" className="mt-6"><Field><FieldLabel htmlFor="text-input">文字内容</FieldLabel><Textarea id="text-input" className="min-h-36" value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴字幕、采访记录或文章内容…" maxLength={2000000} /><FieldDescription>{text.length.toLocaleString()} 字 · 摘要从原文句子中提取</FieldDescription></Field></TabsContent>
                </Tabs>
                {busy && <Alert role="status" aria-live="polite"><LoaderCircle className="spin" size={16} /><AlertTitle>正在处理</AlertTitle><AlertDescription>{job?.message || "正在提交任务"}{job?.browser && <p>{job.browser} · {job.browser_profile}{job.cookie_count > 0 && ` · 已读取 ${job.cookie_count} 条平台 Cookie`}</p>}</AlertDescription></Alert>}
                {error && <Alert variant="destructive"><AlertCircle size={16} /><AlertTitle>处理未完成</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
              </CardContent>
              <CardFooter className="flex flex-wrap justify-between gap-4"><Field className="max-w-40"><FieldLabel htmlFor="language">识别语言</FieldLabel><Select value={language} onValueChange={setLanguage}><SelectTrigger id="language"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="zh">中文</SelectItem><SelectItem value="en">English</SelectItem></SelectGroup></SelectContent></Select></Field><Button type="submit" disabled={!canSubmit || busy} className="min-h-11 self-end">{busy ? <LoaderCircle data-icon="inline-start" className="spin" /> : <Sparkles data-icon="inline-start" />}{busy ? "正在分析" : job?.status === "failed" ? "重试分析" : "开始分析"}<ArrowUpRight data-icon="inline-end" /></Button></CardFooter>
            </form>
          </Card>
          <aside className="flex flex-col gap-4">
            <Card><CardHeader><CardTitle><span className="flex items-center gap-2"><ShieldCheck size={18} />自动使用本机会话</span></CardTitle><CardDescription>不需要手动导出或复制 Cookie。</CardDescription></CardHeader><CardContent><p className="text-sm leading-7 text-muted-foreground">点击分析后，服务会自动读取本机 Chrome、Edge、Brave 或 Firefox 的平台会话，并用隔离浏览器打开视频、获取真实媒体。</p><Separator className="my-4" /><p className="text-sm leading-7 text-muted-foreground">Cookie 不传给页面、不保存为导出文件，仅在请求对应平台时使用。macOS 首次读取可能提示钥匙串授权。</p></CardContent></Card>
            <Card><CardHeader><CardTitle>可回溯的摘要</CardTitle><CardDescription>先转写，再从原文提取重点。</CardDescription></CardHeader><CardContent><p className="text-sm leading-7 text-muted-foreground">当前使用本地语音识别与抽取式摘要。视频的标题、作者、完整转写和时间片段会一同保留，便于检查原意。</p></CardContent></Card>
          </aside>
        </div>
        <section id="results" className="results-section"><div className="results-heading"><div><p className="eyebrow">提取与整理</p><h2>你的内容摘要</h2></div>{result && <Badge variant="secondary"><Check size={14} />已完成</Badge>}</div>
          {result ? <ResultView result={result} /> : <Empty className="border"><EmptyHeader><EmptyMedia variant="icon"><Mic2 /></EmptyMedia><EmptyTitle>{busy ? "正在提取原内容" : "摘要会显示在这里"}</EmptyTitle><EmptyDescription>{busy ? "可查看上方的实时状态，获取视频和本地转写需要一些时间。" : "添加内容后，将展示真实摘要、关键点和转写原文。"}</EmptyDescription></EmptyHeader></Empty>}
        </section>
      </main>
      <footer className="footer"><span>Video AI · 本地内容工作台</span><a href={`${API_URL || "http://127.0.0.1:8765"}/docs`} target="_blank" rel="noreferrer">API 文档 ↗</a></footer>
    </div>
  );
}

/** 功能: 展示真实提取结果；result 为服务完成结果；返回摘要、来源和完整转写。 */
function ResultView({ result }) {
  return <div className="result-grid">
    <Card><CardHeader><CardTitle>{result.title}</CardTitle><CardDescription>{[result.uploader, result.video_id && `视频 ${result.video_id}`].filter(Boolean).join(" · ") || "原文句子提取"}</CardDescription></CardHeader><CardContent className="flex flex-col gap-5"><p className="leading-8">{result.summary}</p><Separator /><h4>关键要点</h4><ul className="flex flex-col gap-3">{result.key_points.map((point, index) => <li key={index} className="flex gap-3"><Check size={16} className="mt-1 shrink-0" /><span className="text-sm leading-7 text-muted-foreground">{point}</span></li>)}</ul><Alert><AlertTitle>阅读提示</AlertTitle><AlertDescription>摘要采用原文抽取，语音转写可能有误，请结合完整原文核对数字、名称和条件。</AlertDescription></Alert></CardContent>{result.source_url && <CardFooter><Button variant="outline" asChild><a href={result.source_url} target="_blank" rel="noreferrer">打开原视频<ArrowUpRight data-icon="inline-end" /></a></Button></CardFooter>}</Card>
    <Card><CardHeader><CardTitle>完整转写</CardTitle><CardDescription>{result.segments.length ? `${result.segments.length} 个时间片段` : "用户提供的文字原文"}</CardDescription></CardHeader><CardContent><div className="transcript">{result.segments.length ? result.segments.map((segment, index) => <p key={index} className="transcript-segment"><time>{formatTime(segment.start_seconds)}</time><span>{segment.text}</span></p>) : <p className="text-sm leading-8 text-muted-foreground">{result.transcript || result.source_excerpt}</p>}</div></CardContent></Card>
  </div>;
}

/** 功能: 格式化时间戳；seconds 为秒数；返回分秒文字。 */
function formatTime(seconds) { return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`; }
