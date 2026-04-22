'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { upsertConceptPolicyAction } from '@/app/actions/concepts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { JSONObject } from '@/types/generated'
import type { ConceptPolicyMode, ConceptPolicyResponse } from '@/types/concepts'

interface ConceptPolicyPanelProps {
  spaceId: string
  canEdit: boolean
  policy: ConceptPolicyResponse | null
  error?: string | null
}

function parsePolicyPayload(value: string): JSONObject | null {
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

export function ConceptPolicyPanel({
  spaceId,
  canEdit,
  policy,
  error,
}: ConceptPolicyPanelProps) {
  const router = useRouter()
  const [mode, setMode] = useState<ConceptPolicyMode>(policy?.mode ?? 'BALANCED')
  const [minimumEdgeConfidence, setMinimumEdgeConfidence] = useState(
    String(policy?.minimum_edge_confidence ?? 0.6),
  )
  const [minimumDistinctDocuments, setMinimumDistinctDocuments] = useState(
    String(policy?.minimum_distinct_documents ?? 1),
  )
  const [allowGenericRelations, setAllowGenericRelations] = useState(
    policy?.allow_generic_relations ?? true,
  )
  const [maxEdgesPerDocument, setMaxEdgesPerDocument] = useState(
    policy?.max_edges_per_document ? String(policy.max_edges_per_document) : '',
  )
  const [policyPayloadJson, setPolicyPayloadJson] = useState(
    JSON.stringify(policy?.policy_payload ?? {}, null, 2),
  )
  const [sourceRef, setSourceRef] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSave = async () => {
    if (!canEdit) {
      toast.error('You do not have permission to update concept policy.')
      return
    }

    const minEdge = Number(minimumEdgeConfidence)
    const minDistinct = Number(minimumDistinctDocuments)
    const maxEdges = maxEdgesPerDocument.trim() ? Number(maxEdgesPerDocument) : null

    if (Number.isNaN(minEdge) || minEdge < 0 || minEdge > 1) {
      toast.error('Minimum edge confidence must be between 0 and 1.')
      return
    }
    if (Number.isNaN(minDistinct) || minDistinct < 1) {
      toast.error('Minimum distinct documents must be >= 1.')
      return
    }
    if (maxEdges !== null && (Number.isNaN(maxEdges) || maxEdges < 1)) {
      toast.error('Max edges per document must be >= 1 when provided.')
      return
    }

    const payload = parsePolicyPayload(policyPayloadJson)
    if (payload === null) {
      toast.error('Policy payload must be a JSON object.')
      return
    }

    setIsSubmitting(true)
    const result = await upsertConceptPolicyAction(spaceId, {
      mode,
      minimum_edge_confidence: minEdge,
      minimum_distinct_documents: Math.floor(minDistinct),
      allow_generic_relations: allowGenericRelations,
      max_edges_per_document: maxEdges === null ? null : Math.floor(maxEdges),
      policy_payload: payload,
      source_ref: sourceRef.trim() || null,
    })
    setIsSubmitting(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Concept policy updated')
    router.refresh()
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Active Policy Profile</CardTitle>
          <CardDescription>
            {error ? <span className="text-destructive">{error}</span> : 'Single profile per research space.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {policy ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{policy.mode}</Badge>
                <Badge variant="outline">Min edge confidence: {policy.minimum_edge_confidence}</Badge>
                <Badge variant="outline">Min docs: {policy.minimum_distinct_documents}</Badge>
              </div>
              <p className="text-muted-foreground">
                Last updated {new Date(policy.updated_at).toLocaleString()} by {policy.created_by}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">No active concept policy yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Update Policy</CardTitle>
          <CardDescription>
            Configure global concept scoring and promotion behavior for this space.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="concept-policy-mode">Mode</Label>
            <Select value={mode} onValueChange={(value: ConceptPolicyMode) => setMode(value)}>
              <SelectTrigger id="concept-policy-mode">
                <SelectValue placeholder="Select mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PRECISION">PRECISION</SelectItem>
                <SelectItem value="BALANCED">BALANCED</SelectItem>
                <SelectItem value="DISCOVERY">DISCOVERY</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-policy-min-edge">Minimum Edge Confidence</Label>
            <Input
              id="concept-policy-min-edge"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minimumEdgeConfidence}
              onChange={(event) => setMinimumEdgeConfidence(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-policy-min-docs">Minimum Distinct Documents</Label>
            <Input
              id="concept-policy-min-docs"
              type="number"
              min={1}
              step={1}
              value={minimumDistinctDocuments}
              onChange={(event) => setMinimumDistinctDocuments(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-policy-max-edges">Max Edges Per Document (optional)</Label>
            <Input
              id="concept-policy-max-edges"
              type="number"
              min={1}
              step={1}
              value={maxEdgesPerDocument}
              onChange={(event) => setMaxEdgesPerDocument(event.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 md:col-span-2">
            <Checkbox
              id="concept-policy-allow-generic"
              checked={allowGenericRelations}
              onCheckedChange={(checked) => setAllowGenericRelations(checked === true)}
            />
            <Label htmlFor="concept-policy-allow-generic">Allow generic relations</Label>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="concept-policy-payload">Policy Payload (JSON object)</Label>
            <Textarea
              id="concept-policy-payload"
              rows={4}
              value={policyPayloadJson}
              onChange={(event) => setPolicyPayloadJson(event.target.value)}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="concept-policy-source-ref">Source Ref (optional)</Label>
            <Input
              id="concept-policy-source-ref"
              value={sourceRef}
              onChange={(event) => setSourceRef(event.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <Button onClick={() => void handleSave()} disabled={!canEdit || isSubmitting}>
              Save Policy
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
