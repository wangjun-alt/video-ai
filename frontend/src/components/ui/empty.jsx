/** 文件: empty.jsx；模块: shadcn 组件；功能: 提供空结果占位；依赖: React、shadcn 公共工具。 */
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/** 功能: 渲染 Empty；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function Empty({
  className,
  ...props
}) {
  return (
    <div
      data-slot="empty"
      className={cn(
        "flex min-w-0 flex-1 flex-col items-center justify-center gap-6 text-balance rounded-lg border-dashed p-6 text-center md:p-12",
        className
      )}
      {...props}
    />
  )
}

/** 功能: 渲染 EmptyHeader；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function EmptyHeader({
  className,
  ...props
}) {
  return (
    <div
      data-slot="empty-header"
      className={cn(
        "flex max-w-sm flex-col items-center gap-2 text-center",
        className
      )}
      {...props}
    />
  )
}

const emptyMediaVariants = cva(
  "mb-2 flex shrink-0 items-center justify-center [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-transparent",
        icon: "bg-muted text-foreground flex size-10 shrink-0 items-center justify-center rounded-lg [&_svg:not([class*='size-'])]:size-6",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

/** 功能: 渲染 EmptyMedia；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function EmptyMedia({
  className,
  variant = "default",
  ...props
}) {
  return (
    <div
      data-slot="empty-icon"
      data-variant={variant}
      className={cn(emptyMediaVariants({ variant, className }))}
      {...props}
    />
  )
}

/** 功能: 渲染 EmptyTitle；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function EmptyTitle({
  className,
  ...props
}) {
  return (
    <div
      data-slot="empty-title"
      className={cn("text-lg font-medium tracking-tight", className)}
      {...props}
    />
  )
}

/** 功能: 渲染 EmptyDescription；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function EmptyDescription({
  className,
  ...props
}) {
  return (
    <div
      data-slot="empty-description"
      className={cn(
        "text-muted-foreground [&>a:hover]:text-primary text-sm/relaxed [&>a]:underline [&>a]:underline-offset-4",
        className
      )}
      {...props}
    />
  )
}

/** 功能: 渲染 EmptyContent；props 包括布局 className、内容 children、交互状态及原生属性，ref 为元素引用；返回界面节点。 */
function EmptyContent({
  className,
  ...props
}) {
  return (
    <div
      data-slot="empty-content"
      className={cn(
        "flex w-full min-w-0 max-w-sm flex-col items-center gap-4 text-balance text-sm",
        className
      )}
      {...props}
    />
  )
}

export {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
  EmptyMedia,
}
