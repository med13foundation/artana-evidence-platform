import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { ALL_FILTER_VALUE } from './hypothesis-utils'

interface HypothesisFiltersProps {
  availableOrigins: string[]
  originFilter: string
  statusFilter: string
  certaintyFilter: string
  setOriginFilterValue: (value: string) => void
  setStatusFilterValue: (value: string) => void
  setCertaintyFilterValue: (value: string) => void
}

export function HypothesisFilters({
  availableOrigins,
  originFilter,
  statusFilter,
  certaintyFilter,
  setOriginFilterValue,
  setStatusFilterValue,
  setCertaintyFilterValue,
}: HypothesisFiltersProps) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <div className="space-y-1">
        <Label>Origin</Label>
        <Select value={originFilter} onValueChange={setOriginFilterValue}>
          <SelectTrigger>
            <SelectValue placeholder="All origins" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
            {availableOrigins.map((origin) => (
              <SelectItem key={origin} value={origin}>
                {origin}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Label>Status</Label>
        <Select value={statusFilter} onValueChange={setStatusFilterValue}>
          <SelectTrigger>
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
            <SelectItem value="OPEN">Open</SelectItem>
            <SelectItem value="NEEDS_MAPPING">Needs Mapping</SelectItem>
            <SelectItem value="REJECTED">Rejected</SelectItem>
            <SelectItem value="RESOLVED">Resolved</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Label>Certainty</Label>
        <Select value={certaintyFilter} onValueChange={setCertaintyFilterValue}>
          <SelectTrigger>
            <SelectValue placeholder="All certainty bands" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
            <SelectItem value="HIGH">High</SelectItem>
            <SelectItem value="MEDIUM">Medium</SelectItem>
            <SelectItem value="LOW">Low</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
