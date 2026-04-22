import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { RelationConstraintListResponse } from '@/types/dictionary'

interface ConstraintsTableCardProps {
  constraints: RelationConstraintListResponse | null
  error?: string | null
}

export function ConstraintsTableCard({ constraints, error }: ConstraintsTableCardProps) {
  const rows = constraints?.constraints ?? []

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Relation Constraints</CardTitle>
        <CardDescription>
          {error ? (
            <span className="text-destructive">{error}</span>
          ) : (
            <span>{rows.length} total</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? null : rows.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            No constraints found.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Relation</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Evidence</TableHead>
                <TableHead>Allowed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono text-xs">{c.source_type}</TableCell>
                  <TableCell className="font-mono text-xs">{c.relation_type}</TableCell>
                  <TableCell className="font-mono text-xs">{c.target_type}</TableCell>
                  <TableCell className="text-xs">
                    {c.requires_evidence ? 'Required' : 'Not required'}
                  </TableCell>
                  <TableCell className="text-xs">
                    {c.is_allowed ? (
                      <Badge>Allowed</Badge>
                    ) : (
                      <Badge variant="destructive">Blocked</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
