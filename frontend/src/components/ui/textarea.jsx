/** 文件: textarea.jsx；模块: shadcn 组件；功能: 提供多行输入；依赖: React、shadcn 公共工具。 */
import * as React from "react"

import { cn } from "@/lib/utils"

/** 功能: 渲染 Textarea；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
const Textarea = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      ref={ref}
      {...props}
    />
  )
})
Textarea.displayName = "Textarea"

export { Textarea }
