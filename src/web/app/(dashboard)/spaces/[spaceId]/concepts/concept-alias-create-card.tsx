'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Link2 } from 'lucide-react'

import { createConceptAliasAction } from '@/app/actions/concepts'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ConceptMemberResponse } from '@/types/concepts'

interface ConceptAliasCreateCardProps {
  spaceId: string
  canEdit: boolean
  conceptMembers: ConceptMemberResponse[]
}

function normalizeLabel(value: string): string {
  return value.trim().toLowerCase()
}

export function ConceptAliasCreateCard({
  spaceId,
  canEdit,
  conceptMembers,
}: ConceptAliasCreateCardProps) {
  const router = useRouter()
  const initialMemberId = useMemo(() => conceptMembers[0]?.id ?? '', [conceptMembers])

  const [aliasMemberId, setAliasMemberId] = useState(initialMemberId)
  const [aliasDomainContext, setAliasDomainContext] = useState('general')
  const [aliasLabel, setAliasLabel] = useState('')
  const [aliasNormalized, setAliasNormalized] = useState('')
  const [aliasSource, setAliasSource] = useState('')
  const [aliasSourceRef, setAliasSourceRef] = useState('')
  const [isCreatingAlias, setIsCreatingAlias] = useState(false)

  const handleCreateAlias = async () => {
    if (!canEdit) {
      toast.error('You do not have permission to create aliases.')
      return
    }
    if (!aliasMemberId || !aliasLabel.trim() || !aliasDomainContext.trim()) {
      toast.error('Concept member, alias label, and domain context are required.')
      return
    }

    const normalized = aliasNormalized.trim() || normalizeLabel(aliasLabel)

    setIsCreatingAlias(true)
    const result = await createConceptAliasAction(spaceId, {
      concept_member_id: aliasMemberId,
      domain_context: aliasDomainContext.trim(),
      alias_label: aliasLabel.trim(),
      alias_normalized: normalized,
      source: aliasSource.trim() || null,
      source_ref: aliasSourceRef.trim() || null,
    })
    setIsCreatingAlias(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Concept alias created')
    setAliasLabel('')
    setAliasNormalized('')
    setAliasSource('')
    setAliasSourceRef('')
    router.refresh()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Create Alias</CardTitle>
        <CardDescription>
          Register normalized synonyms for existing concept members.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="concept-alias-member">Concept Member</Label>
          <Select value={aliasMemberId} onValueChange={setAliasMemberId}>
            <SelectTrigger id="concept-alias-member">
              <SelectValue placeholder="Select member" />
            </SelectTrigger>
            <SelectContent>
              {conceptMembers.map((member) => (
                <SelectItem key={member.id} value={member.id}>
                  {member.canonical_label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-alias-domain">Domain Context</Label>
          <Input
            id="concept-alias-domain"
            value={aliasDomainContext}
            onChange={(event) => setAliasDomainContext(event.target.value)}
            placeholder="biomedical"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-alias-label">Alias Label</Label>
          <Input
            id="concept-alias-label"
            value={aliasLabel}
            onChange={(event) => setAliasLabel(event.target.value)}
            placeholder="MED13"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-alias-normalized">Alias Normalized</Label>
          <Input
            id="concept-alias-normalized"
            value={aliasNormalized}
            onChange={(event) => setAliasNormalized(event.target.value)}
            placeholder="med13"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-alias-source">Alias Source (optional)</Label>
          <Input
            id="concept-alias-source"
            value={aliasSource}
            onChange={(event) => setAliasSource(event.target.value)}
            placeholder="manual"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-alias-source-ref">Source Ref (optional)</Label>
          <Input
            id="concept-alias-source-ref"
            value={aliasSourceRef}
            onChange={(event) => setAliasSourceRef(event.target.value)}
            placeholder="user:curator"
          />
        </div>
        <div className="md:col-span-2">
          <Button
            variant="outline"
            onClick={() => void handleCreateAlias()}
            disabled={!canEdit || conceptMembers.length === 0 || isCreatingAlias}
          >
            <Link2 className="mr-2 size-4" />
            Create Alias
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
