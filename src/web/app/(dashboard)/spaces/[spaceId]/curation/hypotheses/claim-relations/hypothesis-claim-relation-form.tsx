import type { ClaimRelationType, FactAssessment } from '@/types/kernel'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import { CLAIM_RELATION_TYPES, shortId } from './hypothesis-claim-relation-utils'

export interface ClaimRelationOption {
  id: string
  label: string
}

interface HypothesisClaimRelationFormModel {
  claimOptions: ClaimRelationOption[]
  sourceClaimId: string
  targetClaimId: string
  relationType: ClaimRelationType
  supportBand: FactAssessment['support_band']
  isCreating: boolean
  canEdit: boolean
  isLoading: boolean
}

interface HypothesisClaimRelationFormActions {
  setSourceClaimId: (value: string) => void
  setTargetClaimId: (value: string) => void
  setRelationType: (value: ClaimRelationType) => void
  setSupportBand: (value: FactAssessment['support_band']) => void
  createRelation: () => void
  refreshRelations: () => void
}

interface HypothesisClaimRelationFormProps {
  model: HypothesisClaimRelationFormModel
  actions: HypothesisClaimRelationFormActions
}

export function HypothesisClaimRelationForm({ model, actions }: HypothesisClaimRelationFormProps) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="claim-link-source">Source claim</Label>
          <Select value={model.sourceClaimId} onValueChange={actions.setSourceClaimId}>
            <SelectTrigger id="claim-link-source">
              <SelectValue placeholder="Select source hypothesis" />
            </SelectTrigger>
            <SelectContent>
              {model.claimOptions.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {shortId(option.id)} • {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="claim-link-target">Target claim</Label>
          <Select value={model.targetClaimId} onValueChange={actions.setTargetClaimId}>
            <SelectTrigger id="claim-link-target">
              <SelectValue placeholder="Select target hypothesis" />
            </SelectTrigger>
            <SelectContent>
              {model.claimOptions.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {shortId(option.id)} • {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="claim-link-relation-type">Relation type</Label>
          <Select
            value={model.relationType}
            onValueChange={(value) => actions.setRelationType(value as ClaimRelationType)}
          >
            <SelectTrigger id="claim-link-relation-type">
              <SelectValue placeholder="Select relation type" />
            </SelectTrigger>
            <SelectContent>
              {CLAIM_RELATION_TYPES.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="claim-link-support-band">Support strength</Label>
          <Select
            value={model.supportBand}
            onValueChange={(value) => actions.setSupportBand(value as FactAssessment['support_band'])}
          >
            <SelectTrigger id="claim-link-support-band">
              <SelectValue placeholder="Select support strength" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="STRONG">Strong</SelectItem>
              <SelectItem value="SUPPORTED">Supported</SelectItem>
              <SelectItem value="TENTATIVE">Tentative</SelectItem>
              <SelectItem value="INSUFFICIENT">Insufficient</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={actions.createRelation} disabled={model.isCreating || !model.canEdit}>
          {model.isCreating ? 'Linking...' : 'Create claim link'}
        </Button>
        <Button type="button" variant="outline" onClick={actions.refreshRelations} disabled={model.isLoading}>
          Refresh links
        </Button>
      </div>
    </>
  )
}
