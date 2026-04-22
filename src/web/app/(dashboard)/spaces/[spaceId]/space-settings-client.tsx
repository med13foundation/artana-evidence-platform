'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useSpaceContext } from '@/components/space-context-provider'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { updateResearchSpaceAction } from '@/app/actions/research-spaces'
import { Settings } from 'lucide-react'
import type { ResearchSpace } from '@/types/research-space'
import {
  SpaceStatus,
  type ResearchSpaceSettings,
  type UpdateSpaceRequest,
} from '@/types/research-space'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useRouter } from 'next/navigation'

interface SpaceSettingsClientProps {
  spaceId: string
  space: ResearchSpace | null
}

interface SpaceFormState {
  name: string
  slug: string
  description: string
  status: SpaceStatus
  tagsInput: string
}

interface AdvancedSettingsState {
  autoApprove: boolean
  requireReview: boolean
  reviewThreshold: number
  relationGovernanceMode: 'FULL_AUTO' | 'HUMAN_IN_LOOP'
  relationAutoPromotionEnabled: boolean
  relationDefaultReviewThreshold: number
  relationReviewThresholdsText: string
  dictionaryAgentCreationPolicy: 'ACTIVE' | 'PENDING_REVIEW'
  conceptAgentCreationPolicy: 'ACTIVE' | 'PENDING_REVIEW'
  conceptPolicyMode: 'PRECISION' | 'BALANCED' | 'DISCOVERY'
  maxDataSources: number
  allowedSourceTypes: string
  publicRead: boolean
  allowInvites: boolean
  emailNotifications: boolean
  notificationFrequency: string
}

const toFormState = (space?: ResearchSpace): SpaceFormState => ({
  name: space?.name ?? '',
  slug: space?.slug ?? '',
  description: space?.description ?? '',
  status: space?.status ?? SpaceStatus.ACTIVE,
  tagsInput: (space?.tags ?? []).join(', '),
})

const toAdvancedState = (settings?: ResearchSpaceSettings): AdvancedSettingsState => ({
  autoApprove: settings?.auto_approve ?? false,
  requireReview: settings?.require_review ?? true,
  reviewThreshold: settings?.review_threshold ?? 0.8,
  relationGovernanceMode:
    settings?.relation_governance_mode === 'HUMAN_IN_LOOP'
      ? 'HUMAN_IN_LOOP'
      : 'FULL_AUTO',
  relationAutoPromotionEnabled:
    settings?.relation_auto_promotion?.enabled === true,
  relationDefaultReviewThreshold: settings?.relation_default_review_threshold ?? 0.7,
  relationReviewThresholdsText: toThresholdText(settings?.relation_review_thresholds),
  dictionaryAgentCreationPolicy:
    settings?.dictionary_agent_creation_policy === 'PENDING_REVIEW'
      ? 'PENDING_REVIEW'
      : 'ACTIVE',
  conceptAgentCreationPolicy:
    settings?.concept_agent_creation_policy === 'PENDING_REVIEW'
      ? 'PENDING_REVIEW'
      : 'ACTIVE',
  conceptPolicyMode:
    settings?.concept_policy_mode === 'PRECISION'
      ? 'PRECISION'
      : settings?.concept_policy_mode === 'DISCOVERY'
        ? 'DISCOVERY'
        : 'BALANCED',
  maxDataSources: settings?.max_data_sources ?? 25,
  allowedSourceTypes: (settings?.allowed_source_types ?? []).join(', '),
  publicRead: settings?.public_read ?? false,
  allowInvites: settings?.allow_invites ?? true,
  emailNotifications: settings?.email_notifications ?? true,
  notificationFrequency: settings?.notification_frequency ?? 'weekly',
})

export default function SpaceSettingsClient({ spaceId, space }: SpaceSettingsClientProps) {
  const router = useRouter()
  const { setCurrentSpaceId } = useSpaceContext()
  const spaceData = space
  const [formState, setFormState] = useState<SpaceFormState>(() => toFormState(spaceData ?? undefined))
  const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettingsState>(() =>
    toAdvancedState(spaceData?.settings as ResearchSpaceSettings | undefined),
  )
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (spaceId) {
      setCurrentSpaceId(spaceId)
    }
  }, [spaceId, setCurrentSpaceId])

  useEffect(() => {
    setFormState(toFormState(spaceData ?? undefined))
    setAdvancedSettings(toAdvancedState(spaceData?.settings as ResearchSpaceSettings | undefined))
  }, [spaceData])

  const parsedTags = useMemo(
    () =>
      formState.tagsInput
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
    [formState.tagsInput],
  )

  const currentSettings = useMemo(
    () => buildSettingsPayload(advancedSettings),
    [advancedSettings],
  )

  const isDirty = useMemo(() => {
    if (!spaceData) {
      return false
    }
    const tagsChanged =
      parsedTags.length !== spaceData.tags.length ||
      parsedTags.some((tag, index) => tag !== spaceData.tags[index])
    const settingsChanged = !areSettingsEqual(
      currentSettings,
      (spaceData.settings ?? {}) as ResearchSpaceSettings,
    )

    return (
      formState.name !== spaceData.name ||
      formState.slug !== spaceData.slug ||
      formState.description !== (spaceData.description ?? '') ||
      formState.status !== spaceData.status ||
      tagsChanged ||
      settingsChanged
    )
  }, [currentSettings, formState, parsedTags, spaceData])

  const handleChange =
    (field: keyof SpaceFormState) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value = event.target.value
      setFormState((prev) => ({ ...prev, [field]: value }))
    }

  const handleStatusChange = (value: string) => {
    setFormState((prev) => ({ ...prev, status: value as SpaceStatus }))
  }

  const handleAdvancedChange = <K extends keyof AdvancedSettingsState>(
    field: K,
    value: AdvancedSettingsState[K],
  ) => {
    setAdvancedSettings((prev) => ({ ...prev, [field]: value }))
  }

  const handleReset = () => {
    setFormState(toFormState(spaceData ?? undefined))
    setAdvancedSettings(toAdvancedState(spaceData?.settings as ResearchSpaceSettings | undefined))
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!spaceData || !isDirty) {
      return
    }

    const payload: UpdateSpaceRequest = {}
    if (formState.name !== spaceData.name) {
      payload.name = formState.name
    }
    if (formState.slug !== spaceData.slug) {
      payload.slug = formState.slug
    }
    if (formState.description !== (spaceData.description ?? '')) {
      payload.description = formState.description
    }
    if (formState.status !== spaceData.status) {
      payload.status = formState.status
    }
    if (!arraysShallowEqual(parsedTags, spaceData.tags)) {
      payload.tags = parsedTags
    }
    if (
      !areSettingsEqual(
        currentSettings,
        (spaceData.settings ?? {}) as ResearchSpaceSettings,
      )
    ) {
      payload.settings = currentSettings
    }

    try {
      setIsSaving(true)
      const result = await updateResearchSpaceAction(spaceId, payload)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success('Space settings updated')
      router.refresh()
    } catch (error) {
      console.error(error)
      toast.error('Failed to update space settings')
    } finally {
      setIsSaving(false)
    }
  }

  if (!spaceData) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Unable to load this research space. It may have been deleted or you lack permissions.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Space Settings</h1>
        <p className="mt-1 text-muted-foreground">
          Configure settings for {spaceData.name || 'this research space'}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="size-5" />
            General Settings
          </CardTitle>
          <CardDescription>Manage space metadata and behavior.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="space-name">Space Name</Label>
              <Input id="space-name" value={formState.name} onChange={handleChange('name')} required />
            </div>

            <div className="space-y-2">
              <Label htmlFor="space-slug">Slug</Label>
              <Input
                id="space-slug"
                className="font-mono"
                value={formState.slug}
                onChange={handleChange('slug')}
                pattern="^[a-z0-9-]+$"
                title="Lowercase letters, numbers, and hyphens only"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="space-description">Description</Label>
              <Textarea
                id="space-description"
                rows={4}
                value={formState.description}
                onChange={handleChange('description')}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="space-tags">Tags</Label>
              <Input
                id="space-tags"
                value={formState.tagsInput}
                onChange={handleChange('tagsInput')}
                placeholder="med13, cardio, genomics"
              />
              <p className="text-xs text-muted-foreground">Comma-separated list used for filtering.</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="space-status">Status</Label>
              <Select value={formState.status} onValueChange={handleStatusChange}>
                <SelectTrigger id="space-status">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  {Object.values(SpaceStatus).map((status) => (
                    <SelectItem key={status} value={status}>
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Curation Settings</CardTitle>
                <CardDescription>Fine-tune how submissions are reviewed.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ToggleRow
                  label="Auto approve submissions"
                  description="Automatically approve curated items that meet the threshold."
                  checked={advancedSettings.autoApprove}
                  onCheckedChange={(checked) => handleAdvancedChange('autoApprove', checked)}
                />
                <ToggleRow
                  label="Require manual review"
                  description="Ensure reviewers manually review each submission."
                  checked={advancedSettings.requireReview}
                  onCheckedChange={(checked) => handleAdvancedChange('requireReview', checked)}
                />
                <div className="space-y-1">
                  <Label htmlFor="review-threshold">Review Threshold</Label>
                  <Input
                    id="review-threshold"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={advancedSettings.reviewThreshold}
                    onChange={(event) =>
                      handleAdvancedChange('reviewThreshold', Number(event.target.value))
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Minimum confidence score (0–1) before auto approval.
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="relation-governance-mode">Relation governance mode</Label>
                  <Select
                    value={advancedSettings.relationGovernanceMode}
                    onValueChange={(value) =>
                      handleAdvancedChange(
                        'relationGovernanceMode',
                        value as AdvancedSettingsState['relationGovernanceMode'],
                      )
                    }
                  >
                    <SelectTrigger id="relation-governance-mode">
                      <SelectValue placeholder="Select governance mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="FULL_AUTO">FULL_AUTO</SelectItem>
                      <SelectItem value="HUMAN_IN_LOOP">HUMAN_IN_LOOP</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    FULL_AUTO persists accepted relations automatically. HUMAN_IN_LOOP routes
                    uncertain relation outcomes to review.
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="relation-default-threshold">
                    Relation default review threshold
                  </Label>
                  <Input
                    id="relation-default-threshold"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={advancedSettings.relationDefaultReviewThreshold}
                    onChange={(event) =>
                      handleAdvancedChange(
                        'relationDefaultReviewThreshold',
                        Number(event.target.value),
                      )
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="relation-threshold-map">
                    Relation-specific thresholds
                  </Label>
                  <Textarea
                    id="relation-threshold-map"
                    rows={3}
                    value={advancedSettings.relationReviewThresholdsText}
                    onChange={(event) =>
                      handleAdvancedChange('relationReviewThresholdsText', event.target.value)
                    }
                    placeholder="PHYSICALLY_INTERACTS_WITH=0.75, ASSOCIATED_WITH=0.65"
                  />
                  <p className="text-xs text-muted-foreground">
                    Comma-separated relation thresholds in `RELATION_TYPE=value` format.
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="dictionary-agent-creation-policy">
                    Dictionary agent creation policy
                  </Label>
                  <Select
                    value={advancedSettings.dictionaryAgentCreationPolicy}
                    onValueChange={(value) =>
                      handleAdvancedChange(
                        'dictionaryAgentCreationPolicy',
                        value as AdvancedSettingsState['dictionaryAgentCreationPolicy'],
                      )
                    }
                  >
                    <SelectTrigger id="dictionary-agent-creation-policy">
                      <SelectValue placeholder="Select policy" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ACTIVE">ACTIVE</SelectItem>
                      <SelectItem value="PENDING_REVIEW">PENDING_REVIEW</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="concept-agent-creation-policy">
                    Concept agent creation policy
                  </Label>
                  <Select
                    value={advancedSettings.conceptAgentCreationPolicy}
                    onValueChange={(value) =>
                      handleAdvancedChange(
                        'conceptAgentCreationPolicy',
                        value as AdvancedSettingsState['conceptAgentCreationPolicy'],
                      )
                    }
                  >
                    <SelectTrigger id="concept-agent-creation-policy">
                      <SelectValue placeholder="Select policy" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ACTIVE">ACTIVE</SelectItem>
                      <SelectItem value="PENDING_REVIEW">PENDING_REVIEW</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="concept-policy-mode">Concept policy mode</Label>
                  <Select
                    value={advancedSettings.conceptPolicyMode}
                    onValueChange={(value) =>
                      handleAdvancedChange(
                        'conceptPolicyMode',
                        value as AdvancedSettingsState['conceptPolicyMode'],
                      )
                    }
                  >
                    <SelectTrigger id="concept-policy-mode">
                      <SelectValue placeholder="Select concept mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="PRECISION">PRECISION</SelectItem>
                      <SelectItem value="BALANCED">BALANCED</SelectItem>
                      <SelectItem value="DISCOVERY">DISCOVERY</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Data Source Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="max-data-sources">Max Data Sources</Label>
                  <Input
                    id="max-data-sources"
                    type="number"
                    min={1}
                    value={advancedSettings.maxDataSources}
                    onChange={(event) =>
                      handleAdvancedChange('maxDataSources', Number(event.target.value))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="allowed-source-types">Allowed Source Types</Label>
                  <Input
                    id="allowed-source-types"
                    value={advancedSettings.allowedSourceTypes}
                    onChange={(event) =>
                      handleAdvancedChange('allowedSourceTypes', event.target.value)
                    }
                    placeholder="API, CSV, FHIR"
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Access & Notifications</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ToggleRow
                  label="Public read access"
                  description="Allow non-members to view curated data."
                  checked={advancedSettings.publicRead}
                  onCheckedChange={(checked) => handleAdvancedChange('publicRead', checked)}
                />
                <ToggleRow
                  label="Allow member invites"
                  description="Let space members invite new collaborators."
                  checked={advancedSettings.allowInvites}
                  onCheckedChange={(checked) => handleAdvancedChange('allowInvites', checked)}
                />
                <ToggleRow
                  label="Email notifications"
                  description="Send notification emails for important events."
                  checked={advancedSettings.emailNotifications}
                  onCheckedChange={(checked) =>
                    handleAdvancedChange('emailNotifications', checked)
                  }
                />
                <div className="space-y-1">
                  <Label htmlFor="notification-frequency">Notification Frequency</Label>
                  <Select
                    value={advancedSettings.notificationFrequency}
                    onValueChange={(value) => handleAdvancedChange('notificationFrequency', value)}
                  >
                    <SelectTrigger id="notification-frequency">
                      <SelectValue placeholder="Select frequency" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="instant">Instant</SelectItem>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={!isDirty || isSaving}>
                {isSaving ? 'Saving…' : 'Save Changes'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleReset}
                disabled={!isDirty || isSaving}
                className={cn(!isDirty && 'cursor-not-allowed opacity-50')}
              >
                Reset
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

interface ToggleRowProps {
  label: string
  description?: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

function ToggleRow({ label, description, checked, onCheckedChange }: ToggleRowProps) {
  return (
    <label className="flex items-start gap-3">
      <Checkbox
        checked={checked}
        onCheckedChange={onCheckedChange}
        className="mt-1"
      />
      <span>
        <p className="text-sm font-medium leading-none">{label}</p>
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      </span>
    </label>
  )
}

function buildSettingsPayload(state: AdvancedSettingsState): ResearchSpaceSettings {
  return {
    auto_approve: state.autoApprove,
    require_review: state.requireReview,
    review_threshold: state.reviewThreshold,
    relation_governance_mode: state.relationGovernanceMode,
    relation_auto_promotion: {
      enabled: state.relationAutoPromotionEnabled,
    },
    relation_default_review_threshold: state.relationDefaultReviewThreshold,
    relation_review_thresholds: parseThresholdText(state.relationReviewThresholdsText),
    dictionary_agent_creation_policy: state.dictionaryAgentCreationPolicy,
    concept_agent_creation_policy: state.conceptAgentCreationPolicy,
    concept_policy_mode: state.conceptPolicyMode,
    max_data_sources: state.maxDataSources,
    allowed_source_types: state.allowedSourceTypes
      .split(',')
      .map((type) => type.trim())
      .filter(Boolean),
    public_read: state.publicRead,
    allow_invites: state.allowInvites,
    email_notifications: state.emailNotifications,
    notification_frequency: state.notificationFrequency,
  }
}

function areSettingsEqual(
  a: ResearchSpaceSettings,
  b: ResearchSpaceSettings,
): boolean {
  return JSON.stringify(a ?? {}) === JSON.stringify(b ?? {})
}

function arraysShallowEqual<T>(a: T[], b: T[]): boolean {
  if (a.length !== b.length) {
    return false
  }
  return a.every((value, index) => value === b[index])
}

function parseThresholdText(value: string): Record<string, number> {
  const normalizedEntries = value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)

  const thresholds: Record<string, number> = {}
  for (const entry of normalizedEntries) {
    const [rawRelationType, rawThreshold] = entry.split('=', 2)
    if (!rawRelationType || !rawThreshold) {
      continue
    }
    const relationType = rawRelationType.trim().toUpperCase()
    const threshold = Number(rawThreshold.trim())
    if (!relationType || Number.isNaN(threshold)) {
      continue
    }
    thresholds[relationType] = Math.max(0, Math.min(1, threshold))
  }
  return thresholds
}

function toThresholdText(
  value: ResearchSpaceSettings['relation_review_thresholds'] | undefined,
): string {
  if (!value) {
    return ''
  }
  return Object.entries(value)
    .map(([relationType, threshold]) => `${relationType}=${threshold}`)
    .join(', ')
}
