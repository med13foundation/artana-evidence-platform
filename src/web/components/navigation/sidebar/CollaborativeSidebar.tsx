import * as React from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar"
import { MessageSquare, Sparkles } from "lucide-react"

export function CollaborativeSidebar() {
  return (
    <Sidebar side="right" collapsible="offcanvas" className="border-l">
      <SidebarHeader className="flex h-14 items-center border-b px-4">
        <div className="flex items-center gap-2 text-brand-primary">
          <Sparkles className="size-4" />
          <span className="font-heading text-sm font-bold uppercase tracking-widest">Co-Investigator</span>
        </div>
      </SidebarHeader>

      <SidebarContent className="p-4">
        <div className="rounded-2xl border border-dashed border-brand-primary/20 bg-brand-primary/5 p-6 text-center">
          <MessageSquare className="mx-auto mb-3 size-8 text-brand-primary/40" />
          <h3 className="mb-2 font-heading text-sm font-bold">Ready to Collaborate</h3>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Treatment of the AI as a co-investigator is available in Collaborative Mode.
          </p>
        </div>
      </SidebarContent>

      <SidebarFooter className="border-t p-4">
        <div className="text-center text-[10px] uppercase tracking-widest text-muted-foreground">
          Autonomy Level: L1 (Augmented)
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
