/** 文件: separator.jsx；模块: shadcn 组件；功能: 提供内容分隔；依赖: React、shadcn 公共工具。 */
"use client"

import * as React from "react"
import * as SeparatorPrimitive from "@radix-ui/react-separator"

import { cn } from "@/lib/utils"

/** 功能: 渲染 Separator；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
const Separator = React.forwardRef((
  { className, orientation = "horizontal", decorative = true, ...props },
  ref
) => (
  <SeparatorPrimitive.Root
    ref={ref}
    decorative={decorative}
    orientation={orientation}
    className={cn(
      "shrink-0 bg-border",
      orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
      className
    )}
    {...props}
  />
))
Separator.displayName = SeparatorPrimitive.Root.displayName

export { Separator }
