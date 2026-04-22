"use client"

import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { Loader2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { configureDataSourceScheduleAction, updateDataSourceAction } from '@/app/actions/data-sources'
import { runSpaceSourcePipelineAction } from '@/app/actions/kernel-ingest'
import type { DataSource } from '@/types/data-source'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Form } from '@/components/ui/form'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DEFAULT_CLINVAR_AGENT_PROMPT,
  getSourceAgentConfigSnapshot,
} from './sourceAgentConfig'
import {
  AiManagedConfigFields,
  PubMedConfigFields,
} from './DataSourceAiConfigFormFields'
import { DataSourceScheduleFields } from './DataSourceScheduleFields'
import type { AiConfigFormValues } from './DataSourceAiConfigDialog'
import type { ScheduleFormValues } from './DataSourceScheduleDialog'

const aiConfigSchema = z.object({
  use_research_space_context: z.boolean().default(true),
  agent_prompt: z.string().default(''),
  model_id: z.string().nullable().default(null),
  max_results: z.number().int().min(1).max(10000).default(5),
  open_access_only: z.boolean().default(true),
})

const scheduleSchema = z.object({
  enabled: z.boolean().default(true),
  frequency: z.enum(['manual', 'hourly', 'daily', 'weekly', 'monthly', 'cron']),
  startTime: z.string().optional(),
  timezone: z.string().min(1, 'Timezone is required'),
  cronExpression: z.string().optional(),
})

interface DataSourceConfigurationDialogProps {
  source: DataSource | null
  spaceId?: string
  workflowStatus?: {
    last_pipeline_status: string | null
    last_failed_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  }
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTab?: 'schedule' | 'ai'
  activationIntent?: boolean
}

function toLocalDatetimeInput(value?: string | null): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export function DataSourceConfigurationDialog({
  source,
  spaceId,
  workflowStatus,
  open,
  onOpenChange,
  initialTab = 'schedule',
  activationIntent = false,
}: DataSourceConfigurationDialogProps) {
  const router = useRouter()
  const [isSavingSchedule, setIsSavingSchedule] = useState(false)
  const [isSavingAi, setIsSavingAi] = useState(false)
  const [isActivating, setIsActivating] = useState(false)
  const [isRetryingFailedStage, setIsRetryingFailedStage] = useState(false)
  const [scheduleSavedInSession, setScheduleSavedInSession] = useState(false)
  const [aiSavedInSession, setAiSavedInSession] = useState(false)
  const [activeTab, setActiveTab] = useState<'schedule' | 'ai'>(initialTab)

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)

  const schedule = source?.ingestion_schedule
  const scheduleDefaults = useMemo<ScheduleFormValues>(
    () => ({
      enabled: true,
      frequency: schedule?.frequency ?? 'manual',
      startTime: toLocalDatetimeInput(schedule?.start_time),
      timezone: schedule?.timezone ?? 'UTC',
      cronExpression: schedule?.cron_expression ?? '',
    }),
    [schedule],
  )

  const config = isRecord(source?.config) ? source?.config : {}
  const metadata = isRecord(config.metadata) ? config.metadata : {}
  const agentConfig = isRecord(metadata.agent_config) ? metadata.agent_config : {}
  const sourceAgentConfigSnapshot = source
    ? getSourceAgentConfigSnapshot(source)
    : null
  const isPubMedSource = source?.source_type === 'pubmed'
  const queryAgentSourceType = sourceAgentConfigSnapshot?.queryAgentSourceType ?? null
  const sourceQuery =
    typeof metadata.query === 'string'
      ? metadata.query
      : typeof config.query === 'string'
        ? config.query
        : ''
  const defaultAgentPrompt =
    typeof agentConfig.agent_prompt === 'string'
      ? agentConfig.agent_prompt
      : sourceAgentConfigSnapshot?.isClinvarCatalogSource
        ? DEFAULT_CLINVAR_AGENT_PROMPT
        : sourceQuery
  const defaultUseContext =
    typeof agentConfig.use_research_space_context === 'boolean'
      ? agentConfig.use_research_space_context
      : true
  const defaultModelIdFromConfig =
    typeof agentConfig.model_id === 'string' ? agentConfig.model_id : null
  const defaultMaxResults =
    typeof metadata.max_results === 'number' && Number.isFinite(metadata.max_results)
      ? Math.max(1, Math.min(10000, Math.floor(metadata.max_results)))
      : 5
  const defaultOpenAccessOnly = metadata.open_access_only !== false

  const aiDefaults = useMemo<AiConfigFormValues>(
    () => ({
      use_research_space_context: defaultUseContext,
      agent_prompt: defaultAgentPrompt,
      model_id: defaultModelIdFromConfig,
      max_results: defaultMaxResults,
      open_access_only: defaultOpenAccessOnly,
    }),
    [
      defaultAgentPrompt,
      defaultMaxResults,
      defaultModelIdFromConfig,
      defaultOpenAccessOnly,
      defaultUseContext,
    ],
  )

  const scheduleForm = useForm<ScheduleFormValues>({
    resolver: zodResolver(scheduleSchema),
    defaultValues: scheduleDefaults,
  })
  const aiForm = useForm<AiConfigFormValues>({
    resolver: zodResolver(aiConfigSchema),
    defaultValues: aiDefaults,
  })

  useEffect(() => {
    scheduleForm.reset(scheduleDefaults)
    aiForm.reset(aiDefaults)
    if (open) {
      setScheduleSavedInSession(false)
      setAiSavedInSession(false)
    }
  }, [aiDefaults, aiForm, open, scheduleDefaults, scheduleForm])

  useEffect(() => {
    if (open) {
      setActiveTab(initialTab)
    }
  }, [initialTab, open])

  if (!source) {
    return null
  }

  const onSubmitSchedule = async (values: ScheduleFormValues) => {
    const normalizedFrequency = values.frequency === 'manual' ? 'daily' : values.frequency
    const payload = {
      enabled: true,
      frequency: normalizedFrequency,
      timezone: values.timezone,
      start_time: values.startTime ? new Date(values.startTime).toISOString() : null,
      cron_expression:
        normalizedFrequency === 'cron' ? values.cronExpression?.trim() || null : null,
    }

    try {
      setIsSavingSchedule(true)
      const result = await configureDataSourceScheduleAction(source.id, payload, spaceId)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      setScheduleSavedInSession(true)
      toast.success('Schedule updated')
      router.refresh()
    } catch (error) {
      toast.error('Failed to update schedule')
    } finally {
      setIsSavingSchedule(false)
    }
  }

  const onSubmitAi = async (values: AiConfigFormValues) => {
    const updatedAgentConfig: Record<string, unknown> = {
      ...agentConfig,
      is_ai_managed: true,
      agent_prompt: values.agent_prompt,
      use_research_space_context: values.use_research_space_context,
      model_id: values.model_id,
    }
    if (queryAgentSourceType !== null) {
      updatedAgentConfig.query_agent_source_type = queryAgentSourceType
    }
    const updatedMetadata: Record<string, unknown> = {
      ...metadata,
      agent_config: updatedAgentConfig,
    }
    if (isPubMedSource) {
      if (sourceQuery.trim().length > 0) {
        updatedMetadata.query = sourceQuery.trim()
      }
      updatedMetadata.max_results = Math.max(1, Math.min(10000, values.max_results))
      updatedMetadata.open_access_only = true
    }
    const updatedConfig: Record<string, unknown> = {
      ...config,
      metadata: updatedMetadata,
    }
    if (isPubMedSource) {
      if (sourceQuery.trim().length > 0) {
        updatedConfig.query = sourceQuery.trim()
      }
    }

    try {
      setIsSavingAi(true)
      const result = await updateDataSourceAction(
        source.id,
        { config: updatedConfig },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      setAiSavedInSession(true)
      toast.success('AI configuration updated')
      router.refresh()
    } catch (error) {
      toast.error('Failed to update AI configuration')
    } finally {
      setIsSavingAi(false)
    }
  }

  const supportsAiConfiguration = sourceAgentConfigSnapshot?.supportsAiControls ?? false
  const hasRunnablePersistedSchedule =
    source.ingestion_schedule?.enabled === true &&
    String(source.ingestion_schedule.frequency) !== 'manual'
  const hasPersistedAiConfig = isRecord(agentConfig) && Object.keys(agentConfig).length > 0
  const activationRequirements: string[] = []
  if (!hasRunnablePersistedSchedule && !scheduleSavedInSession) {
    activationRequirements.push('Save Schedule (non-manual)')
  }
  if (supportsAiConfiguration && !hasPersistedAiConfig && !aiSavedInSession) {
    activationRequirements.push('Save AI config')
  }
  const canActivate = activationRequirements.length === 0

  const handleActivate = async () => {
    if (!canActivate) {
      toast(`Activation requires: ${activationRequirements.join('; ')}`)
      if (activationRequirements.some((requirement) => requirement.startsWith('Save Schedule'))) {
        setActiveTab('schedule')
      } else {
        setActiveTab('ai')
      }
      return
    }

    try {
      setIsActivating(true)
      const result = await updateDataSourceAction(
        source.id,
        { status: 'active' },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`${source.name} is now active`)
      onOpenChange(false)
      router.refresh()
    } catch (error) {
      toast.error('Failed to activate source')
    } finally {
      setIsActivating(false)
    }
  }

  const handleRetryFailedStage = async () => {
    if (!spaceId) {
      toast.error('Research space is required to retry pipeline.')
      return
    }
    const retryStage = workflowStatus?.last_failed_stage ?? 'ingestion'
    try {
      setIsRetryingFailedStage(true)
      const result = await runSpaceSourcePipelineAction(spaceId, source.id, {
        source_type: source.source_type,
        model_id: defaultModelIdFromConfig,
        resume_from_stage: retryStage,
        force_recover_lock: true,
      })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`Retry queued from ${retryStage} stage.`)
      onOpenChange(false)
      router.refresh()
    } catch {
      toast.error('Failed to retry pipeline from failed stage.')
    } finally {
      setIsRetryingFailedStage(false)
    }
  }

  const canRetryFromFailedStage =
    source.status === 'active' &&
    workflowStatus?.last_pipeline_status === 'failed'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[860px]">
        <DialogHeader>
          <DialogTitle>Configure source</DialogTitle>
          <DialogDescription>
            Manage schedule and AI settings in one place.
          </DialogDescription>
        </DialogHeader>
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'schedule' | 'ai')} className="space-y-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="schedule">Schedule</TabsTrigger>
            <TabsTrigger value="ai">AI config</TabsTrigger>
          </TabsList>

          <TabsContent value="schedule">
            <Form {...scheduleForm}>
              <form className="space-y-4" onSubmit={scheduleForm.handleSubmit(onSubmitSchedule)}>
                <DataSourceScheduleFields
                  control={scheduleForm.control}
                  setValue={scheduleForm.setValue}
                />
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                  <Button type="submit" disabled={isSavingSchedule}>
                    {isSavingSchedule && <Loader2 className="mr-2 size-4 animate-spin" />}
                    Save schedule
                  </Button>
                </div>
              </form>
            </Form>
          </TabsContent>

          <TabsContent value="ai">
            <Form {...aiForm}>
              <form className="space-y-4" onSubmit={aiForm.handleSubmit(onSubmitAi)}>
                <AiManagedConfigFields form={aiForm} isPubMedSource={isPubMedSource} />
                {isPubMedSource && <PubMedConfigFields form={aiForm} />}
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                  <Button type="submit" disabled={isSavingAi}>
                    {isSavingAi && <Loader2 className="mr-2 size-4 animate-spin" />}
                    Save AI config
                  </Button>
                </div>
              </form>
            </Form>
          </TabsContent>
        </Tabs>
        {canRetryFromFailedStage && (
          <div className="mt-2 flex items-center justify-between rounded-md border border-amber-300/60 bg-amber-50/60 p-3">
            <div className="text-sm text-amber-900">
              Last pipeline failed at{' '}
              <span className="font-semibold">
                {workflowStatus?.last_failed_stage ?? 'ingestion'}
              </span>
              . Retry from that stage.
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={handleRetryFailedStage}
              disabled={isRetryingFailedStage}
            >
              {isRetryingFailedStage && (
                <Loader2 className="mr-2 size-4 animate-spin" />
              )}
              Retry failed stage
            </Button>
          </div>
        )}
        {activationIntent && source.status !== 'active' && (
          <div className="mt-2 flex items-center justify-between rounded-md border p-3">
            <div className="text-sm text-muted-foreground">
              Activation requires saved Schedule and AI configuration.
            </div>
            <Button type="button" onClick={handleActivate} disabled={isActivating}>
              {isActivating && <Loader2 className="mr-2 size-4 animate-spin" />}
              Activate source
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
