import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { EntityResolutionPolicyListResponse } from '@/types/dictionary'

interface PoliciesTableCardProps {
  policies: EntityResolutionPolicyListResponse | null
  error?: string | null
}

export function PoliciesTableCard({ policies, error }: PoliciesTableCardProps) {
  const rows = policies?.policies ?? []

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Resolution Policies</CardTitle>
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
            No policies found.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Entity Type</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Required Anchors</TableHead>
                <TableHead>Auto Merge</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.entity_type}>
                  <TableCell className="font-mono text-xs">{p.entity_type}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{p.policy_strategy}</Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    {p.required_anchors.length === 0 ? '—' : p.required_anchors.join(', ')}
                  </TableCell>
                  <TableCell className="text-xs">{p.auto_merge_threshold}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
