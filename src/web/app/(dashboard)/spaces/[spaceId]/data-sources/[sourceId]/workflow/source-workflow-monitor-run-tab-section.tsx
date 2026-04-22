import { ErrorsAndWarningsCard } from './source-workflow-monitor-run-tab-errors'
import { RunMonitorOverview } from './source-workflow-monitor-run-tab-overview'
import { RunMonitorTables } from './source-workflow-monitor-run-tab-tables'
import type { RunMonitorTabSectionProps } from './source-workflow-monitor-run-tab-types'
import { filterWarningRows } from './source-workflow-monitor-warning-rows'

export function RunMonitorTabSection(props: RunMonitorTabSectionProps) {
  const warningRows = filterWarningRows(props.eventRows)
  return (
    <div className="space-y-4">
      <RunMonitorOverview {...props} />
      <RunMonitorTables {...props} />
      <ErrorsAndWarningsCard eventRows={warningRows} warnings={props.warnings} />
    </div>
  )
}
