import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { GraphSearchResponse } from '@/types/kernel'

function confidenceValue(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`
}

interface KnowledgeGraphSearchResultsCardProps {
  graphSearch: GraphSearchResponse | null
}

export function KnowledgeGraphSearchResultsCard({
  graphSearch,
}: KnowledgeGraphSearchResultsCardProps) {
  if (!graphSearch) {
    return null
  }

  const graphSearchResults = graphSearch.results ?? []

  return (
    <Card>
      <CardContent className="py-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Search Results</div>
            <div className="text-xs text-muted-foreground">Query: {graphSearch.original_query}</div>
          </div>
          <Badge variant="outline">Path: {graphSearch.executed_path}</Badge>
        </div>
        {graphSearchResults.length === 0 ? (
          <div className="text-sm text-muted-foreground">No matching entities found.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Entity</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Relevance</TableHead>
                <TableHead>Support</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {graphSearchResults.slice(0, 25).map((result) => (
                <TableRow key={result.entity_id}>
                  <TableCell>
                    <div>{result.display_label ?? '—'}</div>
                    <div className="font-mono text-xs text-muted-foreground">{result.entity_id}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{result.entity_type}</Badge>
                  </TableCell>
                  <TableCell>{confidenceValue(result.relevance_score)}</TableCell>
                  <TableCell className="text-xs">
                    <div>{result.support_summary}</div>
                    <div className="text-muted-foreground">
                      Evidence links: {result.evidence_chain.length}
                    </div>
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
