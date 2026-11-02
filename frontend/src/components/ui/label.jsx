/** 文件: label.jsx；模块: shadcn 组件；功能: 提供表单标签；依赖: React、shadcn 公共工具。 */
import * as React from "react"
import * as LabelPrimitive from "@radix-ui/react-label"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
)

/** 功能: 渲染 Label；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
const Label = React.forwardRef(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
))
Label.displayName = LabelPrimitive.Root.displayName

export { Label }
