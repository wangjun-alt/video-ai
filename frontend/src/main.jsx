/**
 * 文件: src/main.jsx
 * 模块: 前端应用入口
 * 功能: 挂载 Video AI Studio 单页工作台。
 * 依赖: React、ReactDOM
 */

import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
