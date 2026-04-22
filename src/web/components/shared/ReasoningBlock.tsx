import * as React from "react"
import { cn } from "@/lib/utils"
import { Info } from "lucide-react"

interface ReasoningBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string
  icon?: React.ReactNode
}

/**
 * ReasoningBlock - A component to visually set apart AI interpretation
 * or scientific reasoning from raw data.
 *
 * Uses a subtle bg-brand-primary/5 tint (the "scientific highlight").
 */
export function ReasoningBlock({
  title = "Analysis",
  icon = <Info className="size-4" />,
  children,
  className,
  ...props
}: ReasoningBlockProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border border-brand-primary/10 bg-brand-primary/5 p-4 sm:p-5",
        className
      )}
      {...props}
    >
      <div className="mb-2 flex items-center gap-2">
        <div className="flex size-6 items-center justify-center rounded-full bg-brand-primary/10 text-brand-primary">
          {icon}
        </div>
        <span className="font-heading text-xs font-bold uppercase tracking-widest text-brand-primary/80">
          {title}
        </span>
      </div>
      <div className="font-sans text-sm leading-relaxed text-foreground/90">
        {children}
      </div>
    </div>
  )
}
