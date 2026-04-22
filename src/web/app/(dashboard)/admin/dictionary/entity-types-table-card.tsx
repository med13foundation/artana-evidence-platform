import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { DictionaryEntityTypeListResponse } from '@/types/dictionary'

interface EntityTypesTableCardProps {
  entityTypes: DictionaryEntityTypeListResponse | null
  error?: string | null
}

export function EntityTypesTableCard({
  entityTypes,
  error,
}: EntityTypesTableCardProps) {
  const rows = entityTypes?.entity_types ?? []

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Entity Types</CardTitle>
        <CardDescription>
          {error ? <span className="text-destructive">{error}</span> : <span>{rows.length} total</span>}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? null : rows.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            No entity types found.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Display</TableHead>
                <TableHead>Domain</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.id}</TableCell>
                  <TableCell>{row.display_name}</TableCell>
                  <TableCell>{row.domain_context}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{row.review_status}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.is_active ? 'default' : 'secondary'}>
                      {row.is_active ? 'YES' : 'NO'}
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
