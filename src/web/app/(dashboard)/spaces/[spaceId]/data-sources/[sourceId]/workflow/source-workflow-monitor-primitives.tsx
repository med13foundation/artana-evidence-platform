import type { ReactNode } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

import type { MonitorRow } from './source-workflow-monitor-utils'

export interface TableColumn {
  header: string
  className?: string
  render: (row: MonitorRow, index: number) => ReactNode
}

interface TableCardProps {
  title: string
  rows: MonitorRow[]
  columns: TableColumn[]
  emptyText: string
  limit?: number
  rowKey: (row: MonitorRow, index: number) => string
}

export function SummaryRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="grid grid-cols-[220px_1fr] items-start gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-xs' : ''}>{value}</span>
    </div>
  )
}

export function TableCard({
  title,
  rows,
  columns,
  emptyText,
  limit = 20,
  rowKey,
}: TableCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyText}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((column) => (
                  <TableHead key={column.header} className={column.className}>
                    {column.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(0, limit).map((row, index) => (
                <TableRow key={rowKey(row, index)}>
                  {columns.map((column) => (
                    <TableCell key={`${column.header}-${index}`} className={column.className}>
                      {column.render(row, index)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
