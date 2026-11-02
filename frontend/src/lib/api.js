/** 文件: api.js；模块: API 客户端；功能: 请求本地服务并保留准确错误；依赖: 浏览器 Fetch。 */
export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

/** 功能: 请求 JSON；path 为接口路径，options 为 Fetch 选项；返回响应数据，失败抛出原因。 */
export async function requestJson(path, options = {}) {
  let response;
  try {
    const timeout = AbortSignal.timeout(options.body instanceof FormData ? 120000 : 15000);
    const signal = options.signal ? AbortSignal.any([timeout, options.signal]) : timeout;
    response = await fetch(`${API_URL}${path}`, { ...options, signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    if (error.name === "TimeoutError") throw new Error("服务响应超时，请稍后重试");
    throw new Error("无法连接本地服务，请稍后重试");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const error = new Error(typeof detail === "string" ? detail : detail?.[0]?.msg || `服务请求失败（${response.status}）`);
    error.status = response.status;
    throw error;
  }
  return body;
}
