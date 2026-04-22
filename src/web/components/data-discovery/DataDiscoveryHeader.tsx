"use client"

import { Search } from 'lucide-react'

export function DataDiscoveryHeader() {
  return (
    <div className="mb-6 flex flex-col border-b border-border pb-6 md:flex-row md:items-center md:justify-between">
      <div className="mb-4 flex items-center space-x-3 md:mb-0">
        <div className="rounded-lg bg-primary p-2">
          <Search className="size-8 text-primary-foreground" />
        </div>
        <div>
          <h1 className="font-heading text-2xl font-bold text-foreground md:text-3xl">
            Data Source Discovery
          </h1>
          <p className="text-sm text-muted-foreground md:text-base">
            Discover, test, and select biomedical data sources for your research.
          </p>
        </div>
      </div>
      <div className="rounded-lg bg-muted p-2 text-center text-xs text-muted-foreground md:text-right">
        Based on the Data Ecosystem Report for <br />
        <span className="font-semibold text-foreground">MED13-Related Syndrome Research</span>
      </div>
    </div>
  )
}
