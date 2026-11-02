/** 文件: input.jsx；模块: shadcn 组件；功能: 提供单行输入；依赖: React、shadcn 公共工具。 */
import * as React from "react"

import { cn } from "@/lib/utils"

/** 功能: 渲染 Input；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      ref={ref}
      {...props}
    />
  )
})
Input.displayName = "Input"

export { Input }
