/** 文件: utils.js；模块: UI 工具；功能: 合并组件样式；依赖: clsx、tailwind-merge。 */
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** 功能: 合并类名；inputs 为条件样式列表；返回冲突消除后的字符串。 */
export function cn(...inputs) { return twMerge(clsx(inputs)); }
