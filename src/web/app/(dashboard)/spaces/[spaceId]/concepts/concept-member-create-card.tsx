'use client'

import { type FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'

import { createConceptMemberAction } from '@/app/actions/concepts'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { JSONObject } from '@/types/generated'
import type { ConceptSetResponse } from '@/types/concepts'

interface ConceptMemberCreateCardProps {
  spaceId: string
  canEdit: boolean
  conceptSets: ConceptSetResponse[]
}

function normalizeLabel(value: string): string {
  return value.trim().toLowerCase()
}

function parseJsonObject(value: string): JSONObject | null {
  const trimmed = value.trim()
  if (!trimmed) {
    return {}
  }
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return null
    }
    return parsed as JSONObject
  } catch {
    return null
  }
}

export function ConceptMemberCreateCard({
  spaceId,
  canEdit,
  conceptSets,
}: ConceptMemberCreateCardProps) {
  const router = useRouter()
  const [isCreatingMember, setIsCreatingMember] = useState(false)
  const [isProvisional, setIsProvisional] = useState(false)

  const defaultSetId = conceptSets[0]?.id ?? ''

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!canEdit) {
      toast.error('You do not have permission to create members.')
      return
    }

    const formData = new FormData(event.currentTarget)
    const conceptSetId = String(formData.get('concept_set_id') ?? '').trim()
    const domainContext = String(formData.get('domain_context') ?? '').trim()
    const canonicalLabel = String(formData.get('canonical_label') ?? '').trim()
    const normalizedCandidate = String(formData.get('normalized_label') ?? '').trim()

    if (!conceptSetId || !domainContext || !canonicalLabel) {
      toast.error('Concept set, canonical label, and domain context are required.')
      return
    }

    const metadataPayload = parseJsonObject(
      String(formData.get('metadata_json') ?? '{}'),
    )
    if (metadataPayload === null) {
      toast.error('Metadata payload must be a JSON object.')
      return
    }

    const normalizedLabel = normalizedCandidate || normalizeLabel(canonicalLabel)

    setIsCreatingMember(true)
    const result = await createConceptMemberAction(spaceId, {
      concept_set_id: conceptSetId,
      domain_context: domainContext,
      canonical_label: canonicalLabel,
      normalized_label: normalizedLabel,
      sense_key: String(formData.get('sense_key') ?? '').trim(),
      dictionary_dimension: String(formData.get('dictionary_dimension') ?? '').trim() || null,
      dictionary_entry_id: String(formData.get('dictionary_entry_id') ?? '').trim() || null,
      is_provisional: isProvisional,
      metadata_payload: metadataPayload,
      source_ref: String(formData.get('source_ref') ?? '').trim() || null,
    })
    setIsCreatingMember(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Concept member created')
    event.currentTarget.reset()
    setIsProvisional(false)
    router.refresh()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Create Concept Member</CardTitle>
        <CardDescription>
          Add canonical or provisional member entries to concept sets.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void handleSubmit(event)} className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="concept-member-set">Concept Set ID</Label>
            <Input
              id="concept-member-set"
              name="concept_set_id"
              defaultValue={defaultSetId}
              list="concept-set-ids"
              placeholder="UUID"
            />
            <datalist id="concept-set-ids">
              {conceptSets.map((conceptSet) => (
                <option key={conceptSet.id} value={conceptSet.id}>
                  {conceptSet.name}
                </option>
              ))}
            </datalist>
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-domain">Domain Context</Label>
            <Input id="concept-member-domain" name="domain_context" defaultValue="general" placeholder="biomedical" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-canonical">Canonical Label</Label>
            <Input id="concept-member-canonical" name="canonical_label" placeholder="Mediator complex subunit 13" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-normalized">Normalized Label</Label>
            <Input id="concept-member-normalized" name="normalized_label" placeholder="mediator complex subunit 13" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-dimension">Dictionary Dimension (optional)</Label>
            <Input id="concept-member-dimension" name="dictionary_dimension" placeholder="entity_types" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-entry">Dictionary Entry ID (optional)</Label>
            <Input id="concept-member-entry" name="dictionary_entry_id" placeholder="GENE" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-sense">Sense Key (optional)</Label>
            <Input id="concept-member-sense" name="sense_key" placeholder="artana_gene" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-member-source-ref">Source Ref (optional)</Label>
            <Input id="concept-member-source-ref" name="source_ref" placeholder="manual:curation" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="concept-member-metadata">Metadata (JSON object)</Label>
            <Textarea
              id="concept-member-metadata"
              name="metadata_json"
              rows={3}
              defaultValue="{}"
            />
          </div>
          <div className="flex items-center gap-2 md:col-span-2">
            <Checkbox
              id="concept-member-provisional"
              checked={isProvisional}
              onCheckedChange={(checked) => setIsProvisional(checked === true)}
            />
            <Label htmlFor="concept-member-provisional">Create as provisional (pending review)</Label>
          </div>
          <div className="md:col-span-2">
            <Button type="submit" disabled={!canEdit || conceptSets.length === 0 || isCreatingMember}>
              <Plus className="mr-2 size-4" />
              Create Member
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
