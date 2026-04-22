'use client'

import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ConceptMemberResponse, ConceptSetResponse } from '@/types/concepts'

interface ConceptMembersTableCardProps {
  conceptMembers: ConceptMemberResponse[]
  conceptSets: ConceptSetResponse[]
  error?: string | null
}

export function ConceptMembersTableCard({
  conceptMembers,
  conceptSets,
  error,
}: ConceptMembersTableCardProps) {
  const setNameById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const conceptSet of conceptSets) {
      map[conceptSet.id] = conceptSet.name
    }
    return map
  }, [conceptSets])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Members</CardTitle>
        <CardDescription>
          {error ? <span className="text-destructive">{error}</span> : `${conceptMembers.length} total`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? null : conceptMembers.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">No concept members found.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead>Set</TableHead>
                <TableHead>Mapping</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {conceptMembers.map((member) => (
                <TableRow key={member.id}>
                  <TableCell>
                    <p className="font-medium">{member.canonical_label}</p>
                    <p className="text-xs text-muted-foreground">{member.normalized_label}</p>
                  </TableCell>
                  <TableCell>{setNameById[member.concept_set_id] ?? member.concept_set_id}</TableCell>
                  <TableCell className="text-xs">
                    {member.dictionary_dimension && member.dictionary_entry_id
                      ? `${member.dictionary_dimension}:${member.dictionary_entry_id}`
                      : 'provisional'}
                  </TableCell>
                  <TableCell>
                    <Badge variant={member.review_status === 'ACTIVE' ? 'default' : 'secondary'}>
                      {member.review_status}
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
