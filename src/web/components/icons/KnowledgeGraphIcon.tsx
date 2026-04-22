import * as React from "react"
import type { LucideIcon, LucideProps } from "lucide-react"

import { cn } from "@/lib/utils"

const KnowledgeGraphIconBase = React.forwardRef<SVGSVGElement, LucideProps>(
  ({ className, ...props }, ref) => (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("lucide lucide-knowledge-graph", className)}
      {...props}
    >
      <circle cx="12" cy="12" r="3" />
      <circle cx="12" cy="4" r="2" />
      <circle cx="12" cy="20" r="2" />
      <circle cx="19" cy="8" r="2" />
      <circle cx="19" cy="16" r="2" />
      <circle cx="5" cy="8" r="2" />
      <circle cx="5" cy="16" r="2" />
      <line x1="12" y1="9" x2="12" y2="6" />
      <line x1="12" y1="15" x2="12" y2="18" />
      <line x1="14.6" y1="10.5" x2="17.3" y2="9" />
      <line x1="14.6" y1="13.5" x2="17.3" y2="15" />
      <line x1="9.4" y1="10.5" x2="6.7" y2="9" />
      <line x1="9.4" y1="13.5" x2="6.7" y2="15" />
    </svg>
  ),
)

KnowledgeGraphIconBase.displayName = "KnowledgeGraphIcon"

export const KnowledgeGraphIcon = KnowledgeGraphIconBase as LucideIcon
