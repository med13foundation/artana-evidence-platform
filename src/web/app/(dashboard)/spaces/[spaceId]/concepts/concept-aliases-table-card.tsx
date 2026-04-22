'use client'

import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ConceptAliasResponse, ConceptMemberResponse } from '@/types/concepts'

interface ConceptAliasesTableCardProps {
  conceptAliases: ConceptAliasResponse[]
  conceptMembers: ConceptMemberResponse[]
  error?: string | null
}

export function ConceptAliasesTableCard({
  conceptAliases,
  conceptMembers,
  error,
}: ConceptAliasesTableCardProps) {
  const memberLabelById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const member of conceptMembers) {
      map[member.id] = member.canonical_label
    }
    return map
  }, [conceptMembers])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Aliases</CardTitle>
        <CardDescription>
          {error ? <span className="text-destructive">{error}</span> : `${conceptAliases.length} total`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? null : conceptAliases.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">No aliases found.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alias</TableHead>
                <TableHead>Member</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {conceptAliases.map((alias) => (
                <TableRow key={alias.id}>
                  <TableCell>
                    <p className="font-medium">{alias.alias_label}</p>
                    <p className="text-xs text-muted-foreground">{alias.alias_normalized}</p>
                  </TableCell>
                  <TableCell>{memberLabelById[alias.concept_member_id] ?? alias.concept_member_id}</TableCell>
                  <TableCell>{alias.source ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant={alias.review_status === 'ACTIVE' ? 'default' : 'secondary'}>
                      {alias.review_status}
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
