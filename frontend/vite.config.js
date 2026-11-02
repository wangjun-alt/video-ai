/** 文件: vite.config.js；模块: 构建配置；功能: 使用标准 React 编译及本地 API 代理；依赖: Vite。 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/health": "http://127.0.0.1:8765" } },
});
