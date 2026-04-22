"use client"

import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  mergeEntityTypeAction,
  mergeRelationTypeAction,
  mergeVariableAction,
  revokeEntityTypeAction,
  revokeRelationTypeAction,
  revokeVariableAction,
} from '@/app/actions/dictionary-curation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type {
  DictionaryEntityTypeResponse,
  DictionaryRelationTypeResponse,
  VariableDefinitionResponse,
} from '@/types/dictionary'

type DictionaryDimension = 'variables' | 'entity_types' | 'relation_types'

interface DictionaryCurationCardProps {
  variables: VariableDefinitionResponse[]
  entityTypes: DictionaryEntityTypeResponse[]
  relationTypes: DictionaryRelationTypeResponse[]
}

const DIMENSION_LABELS: Record<DictionaryDimension, string> = {
  variables: 'Variable',
  entity_types: 'Entity Type',
  relation_types: 'Relation Type',
}

export function DictionaryCurationCard({
  variables,
  entityTypes,
  relationTypes,
}: DictionaryCurationCardProps) {
  const [dimension, setDimension] = useState<DictionaryDimension>('variables')
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [reason, setReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const idOptions = useMemo(() => {
    if (dimension === 'variables') {
      return variables.map((entry) => entry.id)
    }
    if (dimension === 'entity_types') {
      return entityTypes.map((entry) => entry.id)
    }
    return relationTypes.map((entry) => entry.id)
  }, [dimension, entityTypes, relationTypes, variables])

  const resetInputs = () => {
    setSourceId('')
    setTargetId('')
    setReason('')
  }

  const submitRevoke = async () => {
    if (!sourceId.trim() || !reason.trim()) {
      toast.error('Source ID and reason are required')
      return
    }

    setIsSubmitting(true)
    try {
      let result:
        | Awaited<ReturnType<typeof revokeVariableAction>>
        | Awaited<ReturnType<typeof revokeEntityTypeAction>>
        | Awaited<ReturnType<typeof revokeRelationTypeAction>>

      if (dimension === 'variables') {
        result = await revokeVariableAction(sourceId.trim(), reason.trim())
      } else if (dimension === 'entity_types') {
        result = await revokeEntityTypeAction(sourceId.trim(), reason.trim())
      } else {
        result = await revokeRelationTypeAction(sourceId.trim(), reason.trim())
      }

      if (!result.success) {
        toast.error(result.error)
        return
      }

      toast.success(`${DIMENSION_LABELS[dimension]} revoked`)
      resetInputs()
    } finally {
      setIsSubmitting(false)
    }
  }

  const submitMerge = async () => {
    if (!sourceId.trim() || !targetId.trim() || !reason.trim()) {
      toast.error('Source ID, target ID, and reason are required')
      return
    }
    if (sourceId.trim() === targetId.trim()) {
      toast.error('Source and target IDs must be different')
      return
    }

    setIsSubmitting(true)
    try {
      let result:
        | Awaited<ReturnType<typeof mergeVariableAction>>
        | Awaited<ReturnType<typeof mergeEntityTypeAction>>
        | Awaited<ReturnType<typeof mergeRelationTypeAction>>

      if (dimension === 'variables') {
        result = await mergeVariableAction(sourceId.trim(), targetId.trim(), reason.trim())
      } else if (dimension === 'entity_types') {
        result = await mergeEntityTypeAction(sourceId.trim(), targetId.trim(), reason.trim())
      } else {
        result = await mergeRelationTypeAction(sourceId.trim(), targetId.trim(), reason.trim())
      }

      if (!result.success) {
        toast.error(result.error)
        return
      }

      toast.success(`${DIMENSION_LABELS[dimension]} merged`)
      resetInputs()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Curation Actions</CardTitle>
        <CardDescription>
          Merge or revoke dictionary entries across variables, entity types, and relation types.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="dict-curation-dimension">Dimension</Label>
            <Select
              value={dimension}
              onValueChange={(value: DictionaryDimension) => setDimension(value)}
            >
              <SelectTrigger id="dict-curation-dimension">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="variables">Variables</SelectItem>
                <SelectItem value="entity_types">Entity Types</SelectItem>
                <SelectItem value="relation_types">Relation Types</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="dict-curation-source">Source ID</Label>
            <Input
              id="dict-curation-source"
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
              list="dictionary-id-options"
              placeholder="Entry to revoke or merge"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="dict-curation-target">Merge Target ID</Label>
            <Input
              id="dict-curation-target"
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
              list="dictionary-id-options"
              placeholder="Required for merge"
            />
          </div>
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="dict-curation-reason">Reason</Label>
            <Input
              id="dict-curation-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Required rationale for governance/audit trail"
            />
          </div>
        </div>
        <datalist id="dictionary-id-options">
          {idOptions.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>
        <div className="flex gap-2">
          <Button variant="destructive" disabled={isSubmitting} onClick={() => void submitRevoke()}>
            {isSubmitting ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Revoke
          </Button>
          <Button variant="outline" disabled={isSubmitting} onClick={() => void submitMerge()}>
            {isSubmitting ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Merge
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
