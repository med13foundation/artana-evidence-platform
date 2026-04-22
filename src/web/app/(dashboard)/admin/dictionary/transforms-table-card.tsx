import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { TransformRegistryListResponse } from '@/types/dictionary'

interface TransformsTableCardProps {
  transforms: TransformRegistryListResponse | null
  error?: string | null
}

export function TransformsTableCard({ transforms, error }: TransformsTableCardProps) {
  const rows = transforms?.transforms ?? []

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Transforms</CardTitle>
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
            No transforms found.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Input</TableHead>
                <TableHead>Output</TableHead>
                <TableHead>Implementation</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-mono text-xs">{t.id}</TableCell>
                  <TableCell>{t.input_unit}</TableCell>
                  <TableCell>{t.output_unit}</TableCell>
                  <TableCell className="font-mono text-xs">{t.implementation_ref}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{t.status}</Badge>
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
