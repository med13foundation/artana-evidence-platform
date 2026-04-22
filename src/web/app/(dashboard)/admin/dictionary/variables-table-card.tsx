import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { VariableDefinitionListResponse } from '@/types/dictionary'

interface VariablesTableCardProps {
  variables: VariableDefinitionListResponse | null
  error?: string | null
}

export function VariablesTableCard({ variables, error }: VariablesTableCardProps) {
  const rows = variables?.variables ?? []

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Variables</CardTitle>
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
            No variables found.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Canonical</TableHead>
                <TableHead>Display</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Domain</TableHead>
                <TableHead>Sensitivity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((v) => (
                <TableRow key={v.id}>
                  <TableCell className="font-mono text-xs">{v.id}</TableCell>
                  <TableCell className="font-mono text-xs">{v.canonical_name}</TableCell>
                  <TableCell>{v.display_name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{v.data_type}</Badge>
                  </TableCell>
                  <TableCell>{v.domain_context}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{v.sensitivity}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{v.review_status}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={v.is_active ? 'default' : 'secondary'}>
                      {v.is_active ? 'YES' : 'NO'}
                    </Badge>
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
