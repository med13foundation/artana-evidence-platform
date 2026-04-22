'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { GitPullRequest } from 'lucide-react'

import { proposeConceptDecisionAction } from '@/app/actions/concepts'
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
import { Textarea } from '@/components/ui/textarea'
import type { JSONObject } from '@/types/generated'
import type { ConceptDecisionType, ConceptMemberResponse, ConceptSetResponse } from '@/types/concepts'

interface ConceptDecisionProposeCardProps {
  spaceId: string
  canPropose: boolean
  conceptSets: ConceptSetResponse[]
  conceptMembers: ConceptMemberResponse[]
}

const DECISION_TYPES: ConceptDecisionType[] = [
  'CREATE',
  'MAP',
  'MERGE',
  'SPLIT',
  'LINK',
  'PROMOTE',
  'DEMOTE',
]

function parseObject(value: string): JSONObject | null {
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

export function ConceptDecisionProposeCard({
  spaceId,
  canPropose,
  conceptSets,
  conceptMembers,
}: ConceptDecisionProposeCardProps) {
  const router = useRouter()

  const [decisionType, setDecisionType] = useState<ConceptDecisionType>('CREATE')
  const [conceptSetId, setConceptSetId] = useState('')
  const [conceptMemberId, setConceptMemberId] = useState('')
  const [conceptLinkId, setConceptLinkId] = useState('')
  const [confidence, setConfidence] = useState('')
  const [rationale, setRationale] = useState('')
  const [decisionPayloadJson, setDecisionPayloadJson] = useState('{}')
  const [evidencePayloadJson, setEvidencePayloadJson] = useState('{}')
  const [isProposing, setIsProposing] = useState(false)

  const handlePropose = async () => {
    if (!canPropose) {
      toast.error('You do not have permission to propose decisions.')
      return
    }

    const parsedDecisionPayload = parseObject(decisionPayloadJson)
    const parsedEvidencePayload = parseObject(evidencePayloadJson)
    if (parsedDecisionPayload === null || parsedEvidencePayload === null) {
      toast.error('Decision and evidence payloads must be JSON objects.')
      return
    }

    const parsedConfidence = confidence.trim().length > 0 ? Number(confidence) : null
    if (parsedConfidence !== null && (Number.isNaN(parsedConfidence) || parsedConfidence < 0 || parsedConfidence > 1)) {
      toast.error('Confidence must be between 0 and 1 when provided.')
      return
    }

    setIsProposing(true)
    const result = await proposeConceptDecisionAction(spaceId, {
      decision_type: decisionType,
      decision_payload: parsedDecisionPayload,
      evidence_payload: parsedEvidencePayload,
      confidence: parsedConfidence,
      rationale: rationale.trim() || null,
      concept_set_id: conceptSetId || null,
      concept_member_id: conceptMemberId || null,
      concept_link_id: conceptLinkId.trim() || null,
    })
    setIsProposing(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success(`Decision proposed (${result.data.decision_status})`)
    setConfidence('')
    setRationale('')
    setConceptLinkId('')
    setDecisionPayloadJson('{}')
    setEvidencePayloadJson('{}')
    router.refresh()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Propose Decision</CardTitle>
        <CardDescription>
          Create a governance decision payload for harness evaluation and review.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="concept-decision-type">Decision Type</Label>
          <Select value={decisionType} onValueChange={(value: ConceptDecisionType) => setDecisionType(value)}>
            <SelectTrigger id="concept-decision-type">
              <SelectValue placeholder="Select decision type" />
            </SelectTrigger>
            <SelectContent>
              {DECISION_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-decision-confidence">Confidence (optional)</Label>
          <Input
            id="concept-decision-confidence"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(event) => setConfidence(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-decision-set">Concept Set (optional)</Label>
          <Select value={conceptSetId} onValueChange={setConceptSetId}>
            <SelectTrigger id="concept-decision-set">
              <SelectValue placeholder="Select concept set" />
            </SelectTrigger>
            <SelectContent>
              {conceptSets.map((conceptSet) => (
                <SelectItem key={conceptSet.id} value={conceptSet.id}>
                  {conceptSet.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="concept-decision-member">Concept Member (optional)</Label>
          <Select value={conceptMemberId} onValueChange={setConceptMemberId}>
            <SelectTrigger id="concept-decision-member">
              <SelectValue placeholder="Select concept member" />
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
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="concept-decision-link-id">Concept Link ID (optional)</Label>
          <Input
            id="concept-decision-link-id"
            value={conceptLinkId}
            onChange={(event) => setConceptLinkId(event.target.value)}
            placeholder="UUID of related concept link"
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="concept-decision-rationale">Rationale (optional)</Label>
          <Textarea
            id="concept-decision-rationale"
            rows={3}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder="Why this decision should apply"
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="concept-decision-payload">Decision Payload (JSON object)</Label>
          <Textarea
            id="concept-decision-payload"
            rows={4}
            value={decisionPayloadJson}
            onChange={(event) => setDecisionPayloadJson(event.target.value)}
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="concept-evidence-payload">Evidence Payload (JSON object)</Label>
          <Textarea
            id="concept-evidence-payload"
            rows={4}
            value={evidencePayloadJson}
            onChange={(event) => setEvidencePayloadJson(event.target.value)}
          />
        </div>
        <div className="md:col-span-2">
          <Button onClick={() => void handlePropose()} disabled={!canPropose || isProposing}>
            <GitPullRequest className="mr-2 size-4" />
            Propose Decision
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
