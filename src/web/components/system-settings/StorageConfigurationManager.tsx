"use client"

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'
import {
  AlertCircle,
  BarChart3,
  HardDrive,
  Loader2,
  ShieldCheck,
  TestTube,
  Trash2,
  TrendingUp,
} from 'lucide-react'
import {
  createStorageConfigurationAction,
  deleteStorageConfigurationAction,
  testStorageConfigurationAction,
  updateStorageConfigurationAction,
} from '@/app/actions/storage'
import type {
  CreateStorageConfigurationRequest,
  StorageConfiguration,
  StorageConfigurationStats,
  StorageOverviewResponse,
  StorageProviderConfig,
  StorageHealthReport,
  StorageUsageMetrics,
  StorageUseCase,
} from '@/types/storage'
import { STORAGE_PROVIDERS, STORAGE_USE_CASES } from '@/types/storage'
import { cn } from '@/lib/utils'
import type { StorageConfigurationListResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import { queryKeys } from '@/lib/query/query-keys'
import {
  storageConfigurationsQueryOptions,
  storageOverviewQueryOptions,
} from '@/lib/query/query-options'

const storageUseCaseEnum = z.enum(STORAGE_USE_CASES)
const STORAGE_DASHBOARD_BETA =
  typeof process !== 'undefined' && process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA === 'true'

const localConfigSchema = z.object({
  provider: z.literal('local_filesystem'),
  name: z.string().min(3, 'Name must be at least 3 characters long'),
  default_use_cases: z.array(storageUseCaseEnum).min(1, 'Select at least one use case'),
  base_path: z.string().min(1, 'Base path is required'),
  create_directories: z.boolean().default(true),
  expose_file_urls: z.boolean().default(false),
  enabled: z.boolean().default(true),
})

const gcsConfigSchema = z.object({
  provider: z.literal('google_cloud_storage'),
  name: z.string().min(3, 'Name must be at least 3 characters long'),
  default_use_cases: z.array(storageUseCaseEnum).min(1, 'Select at least one use case'),
  bucket_name: z.string().min(3, 'Bucket name is required'),
  base_path: z.string().default('/'),
  credentials_secret_name: z.string().min(3, 'Secret name is required'),
  public_read: z.boolean().default(false),
  signed_url_ttl_seconds: z.coerce
    .number()
    .min(60, 'TTL must be at least 60 seconds')
    .max(86_400, 'TTL cannot exceed 24 hours')
    .default(3600),
  enabled: z.boolean().default(true),
})

const storageFormSchema = z.discriminatedUnion('provider', [
  localConfigSchema,
  gcsConfigSchema,
])

type StorageFormValues = z.infer<typeof storageFormSchema>
const DEFAULT_LOCAL_BASE_PATH = '/var/artana/storage'
const DEFAULT_GCS_BASE_PATH = '/'

const providerLabels: Record<StorageFormValues['provider'], string> = {
  local_filesystem: 'Local Filesystem',
  google_cloud_storage: 'Google Cloud Storage',
}

const useCaseLabels: Record<StorageUseCase, string> = {
  pdf: 'PubMed PDFs',
  export: 'Exports',
  raw_source: 'Raw Source Payloads',
  backup: 'Backups',
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(1)} ${units[exponent]}`
}

interface StorageConfigurationCardProps {
  configuration: StorageConfiguration
  usage: StorageUsageMetrics | null
  health: StorageHealthReport | null
  isToggling: boolean
  onToggleEnabled: (
    configuration: StorageConfiguration,
    enabled: boolean,
    hasUsage: boolean,
  ) => Promise<void>
  onTestConnection: (configuration: StorageConfiguration) => Promise<void>
  isTesting: boolean
  isSelected: boolean
  onSelectionChange: (configurationId: string, selected: boolean) => void
  onDelete: (configuration: StorageConfiguration, hasUsage: boolean) => Promise<void>
  isDeleting: boolean
  enableSelection: boolean
}

function StorageConfigurationCard({
  configuration,
  usage,
  health,
  onToggleEnabled,
  isToggling,
  onTestConnection,
  isTesting,
  isSelected,
  onSelectionChange,
  onDelete,
  isDeleting,
  enableSelection,
}: StorageConfigurationCardProps) {
  const totalFiles = usage?.total_files ?? 0

  const handleToggle = async (checked: boolean) => {
    await onToggleEnabled(configuration, checked, totalFiles > 0)
  }

  const handleDelete = async () => {
    await onDelete(configuration, totalFiles > 0)
  }

  return (
    <Card data-testid={`storage-card-${configuration.id}`}>
      <CardHeader className="flex flex-col gap-4 border-b border-border/50 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="size-4 text-muted-foreground" />
            {configuration.name}
          </CardTitle>
          <CardDescription>{providerLabels[configuration.provider]}</CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {enableSelection && (
            <Button
              type="button"
              size="sm"
              variant={isSelected ? 'default' : 'outline'}
              onClick={() => onSelectionChange(configuration.id, !isSelected)}
            >
              {isSelected ? 'Selected' : 'Select'}
            </Button>
          )}
          <Switch
            checked={configuration.enabled}
            onCheckedChange={handleToggle}
            disabled={isToggling}
            id={`storage-toggle-${configuration.id}`}
          />
          <Label
            htmlFor={`storage-toggle-${configuration.id}`}
            className={cn('text-sm', !configuration.enabled && 'text-muted-foreground')}
          >
            {configuration.enabled ? 'Enabled' : 'Disabled'}
          </Label>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {configuration.default_use_cases.map((useCase) => (
            <Badge key={useCase} variant="secondary">
              {useCaseLabels[useCase]}
            </Badge>
          ))}
        </div>
        <div className="text-sm text-muted-foreground">
          <div>Capabilities: {configuration.supported_capabilities.join(', ') || 'n/a'}</div>
          {'base_path' in configuration.config && (
            <div>Base Path: {configuration.config.base_path}</div>
          )}
          {'bucket_name' in configuration.config && (
            <div>Bucket: {configuration.config.bucket_name}</div>
          )}
        </div>
        <Separator />
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Health</p>
            <p className="flex items-center gap-2 font-medium">
              <ShieldCheck
                className={cn('size-4', {
                  'text-emerald-500': health?.status === 'healthy',
                  'text-amber-500': health?.status === 'degraded',
                  'text-destructive': health?.status === 'offline',
                })}
              />
              {health?.status ?? 'Unknown'}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Files Managed</p>
            <p className="font-medium">{totalFiles}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Error Rate</p>
            <p className="font-medium">
              {usage?.error_rate
                ? `${(usage.error_rate * 100).toFixed(1)}%`
                : '0%'}
            </p>
          </div>
        </div>
      </CardContent>
      <CardFooter className="flex flex-wrap justify-end gap-3 border-t border-border/50 pt-4">
        <Button
          variant="outline"
          onClick={() => onTestConnection(configuration)}
          disabled={isTesting}
        >
          {isTesting ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              Testing...
            </>
          ) : (
            <>
              <TestTube className="mr-2 size-4" />
              Test Connection
            </>
          )}
        </Button>
        <Button
          variant="destructive"
          onClick={handleDelete}
          disabled={isDeleting}
        >
          {isDeleting ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              Removing...
            </>
          ) : (
            <>
              <Trash2 className="mr-2 size-4" />
              Delete
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  )
}

function StorageTrendPlaceholder({ overview }: { overview: StorageOverviewResponse }) {
  const points = useMemo(() => {
    const usageValues =
      overview.configurations
        .map((entry) => entry.usage?.total_files ?? 0)
        .filter((value) => value > 0) || []
    if (usageValues.length === 0) {
      return Array.from({ length: 7 }, (_, index) => (index + 1) * 10)
    }
    const base = usageValues.reduce((sum, value) => sum + value, 0) / usageValues.length
    return Array.from({ length: 7 }, (_, index) =>
      Math.max(5, Math.round(base * (1 + index / 10))),
    )
  }, [overview.configurations])
  const maxValue = Math.max(...points, 1)
  return (
    <div className="space-y-2">
      <div className="flex h-24 items-end gap-2">
        {points.map((value, index) => (
          <div
            key={`trend-${index}`}
            className="flex-1 rounded bg-primary/30"
            style={{ height: `${Math.max(8, (value / maxValue) * 100)}%` }}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">Rolling seven day ingest estimate</p>
    </div>
  )
}

function StorageOverviewSection({
  overview,
  showBeta,
}: {
  overview: StorageOverviewResponse
  showBeta: boolean
}) {
  const topConfigurations = useMemo(() => {
    return overview.configurations
      .slice()
      .sort((a, b) => (b.usage?.total_files ?? 0) - (a.usage?.total_files ?? 0))
      .slice(0, 3)
  }, [overview.configurations])

  const avgFilesPerConfig = overview.totals.enabled_configurations
    ? Math.round(overview.totals.total_files / overview.totals.enabled_configurations)
    : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="size-4 text-muted-foreground" />
          Storage Platform Overview
        </CardTitle>
        <CardDescription>
          Updated {new Date(overview.generated_at).toLocaleTimeString()} – capacity forecasting and
          recent usage trends.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Enabled configurations</p>
            <p className="font-heading text-2xl font-semibold">
              {overview.totals.enabled_configurations} / {overview.totals.total_configurations}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Files managed</p>
            <p className="font-heading text-2xl font-semibold">{overview.totals.total_files.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Storage consumed</p>
            <p className="font-heading text-2xl font-semibold">
              {formatBytes(overview.totals.total_size_bytes)}
            </p>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-dashed bg-muted/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="size-4 text-muted-foreground" />
                Capacity planning
              </CardTitle>
              <CardDescription>
                Average of {avgFilesPerConfig.toLocaleString()} files per active configuration.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Healthy: {overview.totals.healthy_configurations} • Degraded: {overview.totals.degraded_configurations} •
                Offline: {overview.totals.offline_configurations}
              </p>
            </CardContent>
          </Card>
          <Card className="border-dashed">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck className="size-4 text-muted-foreground" />
                Top configurations
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {topConfigurations.map((entry) => (
                <div key={entry.configuration.id} className="flex items-center justify-between text-sm">
                  <div>
                    <p className="font-medium">{entry.configuration.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {entry.usage?.total_files.toLocaleString() ?? 0} files •{' '}
                      {entry.health?.status ?? 'unknown'}
                    </p>
                  </div>
                  <span className="text-xs font-semibold">
                    {formatBytes(entry.usage?.total_size_bytes ?? 0)}
                  </span>
                </div>
              ))}
              {topConfigurations.length === 0 && (
                <p className="text-sm text-muted-foreground">No usage data yet.</p>
              )}
            </CardContent>
          </Card>
          {showBeta && (
            <Card className="border-dashed bg-card/50 md:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Daily storage throughput</CardTitle>
                <CardDescription>Beta visualization powered by aggregated totals.</CardDescription>
              </CardHeader>
              <CardContent>
                <StorageTrendPlaceholder overview={overview} />
              </CardContent>
            </Card>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function BulkActionBar({
  count,
  onClear,
  onEnable,
  onDisable,
  onDelete,
  isProcessing,
  showBeta,
}: {
  count: number
  onClear: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
  isProcessing: boolean
  showBeta: boolean
}) {
  if (count === 0 || !showBeta) {
    return null
  }

  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="text-sm font-medium">
          {count} configuration{count === 1 ? '' : 's'} selected
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onEnable} disabled={isProcessing}>
            Enable
          </Button>
          <Button variant="outline" size="sm" onClick={onDisable} disabled={isProcessing}>
            Disable
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete} disabled={isProcessing}>
            Delete
          </Button>
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

interface StorageConfigurationManagerProps {
  configurations: StorageConfigurationListResponse | null
  overview: StorageOverviewResponse | null
  maintenanceState: MaintenanceModeResponse | null
}

const STORAGE_QUERY_PARAMS = {
  page: 1,
  per_page: 100,
  include_disabled: true,
} as const

function upsertOverviewConfiguration(
  overview: StorageOverviewResponse,
  configuration: StorageConfiguration,
): StorageOverviewResponse {
  const existingEntry = overview.configurations.find(
    (entry) => entry.configuration.id === configuration.id,
  )
  const configurations = existingEntry
    ? overview.configurations.map((entry) =>
        entry.configuration.id === configuration.id
          ? { ...entry, configuration }
          : entry,
      )
    : [{ configuration, usage: null, health: null }, ...overview.configurations]

  const enabledDelta = existingEntry
    ? Number(configuration.enabled) - Number(existingEntry.configuration.enabled)
    : Number(configuration.enabled)
  const disabledDelta = existingEntry ? -enabledDelta : Number(!configuration.enabled)

  return {
    ...overview,
    configurations,
    totals: {
      ...overview.totals,
      total_configurations: existingEntry
        ? overview.totals.total_configurations
        : overview.totals.total_configurations + 1,
      enabled_configurations: Math.max(overview.totals.enabled_configurations + enabledDelta, 0),
      disabled_configurations: Math.max(overview.totals.disabled_configurations + disabledDelta, 0),
    },
  }
}

function removeOverviewConfiguration(
  overview: StorageOverviewResponse,
  configurationId: string,
): StorageOverviewResponse {
  const existingEntry = overview.configurations.find(
    (entry) => entry.configuration.id === configurationId,
  )
  if (!existingEntry) {
    return overview
  }

  const { usage, health, configuration } = existingEntry

  return {
    ...overview,
    configurations: overview.configurations.filter(
      (entry) => entry.configuration.id !== configurationId,
    ),
    totals: {
      ...overview.totals,
      total_configurations: Math.max(overview.totals.total_configurations - 1, 0),
      enabled_configurations: Math.max(
        overview.totals.enabled_configurations - Number(configuration.enabled),
        0,
      ),
      disabled_configurations: Math.max(
        overview.totals.disabled_configurations - Number(!configuration.enabled),
        0,
      ),
      healthy_configurations: Math.max(
        overview.totals.healthy_configurations - Number(health?.status === 'healthy'),
        0,
      ),
      degraded_configurations: Math.max(
        overview.totals.degraded_configurations - Number(health?.status === 'degraded'),
        0,
      ),
      offline_configurations: Math.max(
        overview.totals.offline_configurations - Number(health?.status === 'offline'),
        0,
      ),
      total_files: Math.max(overview.totals.total_files - (usage?.total_files ?? 0), 0),
      total_size_bytes: Math.max(
        overview.totals.total_size_bytes - (usage?.total_size_bytes ?? 0),
        0,
      ),
    },
  }
}

export function StorageConfigurationManager({
  configurations: configurationResponse,
  overview,
  maintenanceState,
}: StorageConfigurationManagerProps) {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [bulkAction, setBulkAction] = useState<'enable' | 'disable' | 'delete' | null>(null)
  const isMaintenanceActive = maintenanceState?.state.is_active ?? false
  const maintenanceStateLoading = maintenanceState === null
  const [pendingCreate, setPendingCreate] = useState<StorageFormValues | null>(null)
  const [maintenanceModalOpen, setMaintenanceModalOpen] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const showDashboardBeta = STORAGE_DASHBOARD_BETA

  const form = useForm<StorageFormValues>({
    resolver: zodResolver(storageFormSchema),
    defaultValues: {
      provider: 'local_filesystem',
      name: '',
      base_path: DEFAULT_LOCAL_BASE_PATH,
      create_directories: true,
      expose_file_urls: false,
      default_use_cases: ['pdf'],
      enabled: true,
    } as StorageFormValues,
  })

  const configurationQuery = useQuery(
    storageConfigurationsQueryOptions(STORAGE_QUERY_PARAMS, configurationResponse ?? undefined),
  )
  const overviewQuery = useQuery(storageOverviewQueryOptions(overview ?? undefined))
  const configurationData = configurationQuery.data ?? configurationResponse
  const resolvedOverview = overviewQuery.data ?? overview
  const selectedProvider = form.watch('provider')
  const configurations = useMemo(
    () => configurationData?.data ?? [],
    [configurationData?.data],
  )
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const overviewMap = useMemo(() => {
    const map = new Map<string, StorageConfigurationStats>()
    resolvedOverview?.configurations.forEach((entry) => {
      map.set(entry.configuration.id, entry)
    })
    return map
  }, [resolvedOverview])

  useEffect(() => {
    if (!configurations.length && selectedIds.length) {
      setSelectedIds([])
    } else {
      const configurationIds = new Set(configurations.map((item) => item.id))
      setSelectedIds((current) => current.filter((id) => configurationIds.has(id)))
    }
  }, [configurations, selectedIds.length])

  const submitConfiguration = async (values: StorageFormValues) => {
    const payload = convertFormToPayload(values)
    try {
      setIsCreating(true)
      const result = await createStorageConfigurationAction(payload)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      queryClient.setQueryData<StorageConfigurationListResponse>(
        queryKeys.storageConfigurations(STORAGE_QUERY_PARAMS),
        (current) =>
          current === undefined
            ? current
            : {
                ...current,
                data: [result.data, ...current.data.filter((entry) => entry.id !== result.data.id)],
                total: current.data.some((entry) => entry.id === result.data.id)
                  ? current.total
                  : current.total + 1,
              },
      )
      queryClient.setQueryData<StorageOverviewResponse>(
        queryKeys.storageOverview(),
        (current) => (current === undefined ? current : upsertOverviewConfiguration(current, result.data)),
      )
      toast.success(`Created storage configuration "${values.name}"`)
      form.reset()
      setDialogOpen(false)
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.storageConfigurationsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.storageOverview() }),
      ])
    } catch (error) {
      console.error('[StorageConfigurationManager] Failed to create configuration', error)
      toast.error('Unable to create storage configuration')
    } finally {
      setIsCreating(false)
    }
  }

  const requireMaintenance = (): boolean => {
    if (maintenanceStateLoading) {
      toast.error('Maintenance status is still loading. Please try again.')
      return true
    }
    return false
  }

  const updateConfigurationEnabled = async (
    configuration: StorageConfiguration,
    enabled: boolean,
    hasUsage: boolean,
  ) => {
    if (requireMaintenance()) {
      return
    }
    if (hasUsage && !isMaintenanceActive) {
      toast.error('Enable maintenance mode before changing a storage backend in use.')
      return
    }
    setTogglingId(configuration.id)
    try {
      const result = await updateStorageConfigurationAction(configuration.id, { enabled })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      queryClient.setQueryData<StorageConfigurationListResponse>(
        queryKeys.storageConfigurations(STORAGE_QUERY_PARAMS),
        (current) =>
          current === undefined
            ? current
            : {
                ...current,
                data: current.data.map((entry) =>
                  entry.id === result.data.id ? result.data : entry,
                ),
              },
      )
      queryClient.setQueryData<StorageOverviewResponse>(
        queryKeys.storageOverview(),
        (current) => (current === undefined ? current : upsertOverviewConfiguration(current, result.data)),
      )
      toast.success(`${configuration.name} ${enabled ? 'enabled' : 'disabled'}`)
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.storageConfigurationsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.storageOverview() }),
      ])
    } catch (error) {
      console.error('[StorageConfigurationManager] Failed to toggle configuration', error)
      toast.error('Unable to update configuration status')
    } finally {
      setTogglingId(null)
    }
  }

  const handleCreate = async (values: StorageFormValues) => {
    const hasEnabledConfig = configurations.some((config) => config.enabled)
    const providerChanged = values.provider !== 'local_filesystem'
    const basePathChanged =
      (values.provider === 'local_filesystem' && values.base_path !== DEFAULT_LOCAL_BASE_PATH) ||
      (values.provider === 'google_cloud_storage' && values.base_path !== DEFAULT_GCS_BASE_PATH)

    if (!isMaintenanceActive && hasEnabledConfig && (providerChanged || basePathChanged)) {
      setPendingCreate(values)
      setMaintenanceModalOpen(true)
      return
    }

    await submitConfiguration(values)
  }

  const handleTestConnection = async (configuration: StorageConfiguration) => {
    setTestingId(configuration.id)
    try {
      const result = await testStorageConfigurationAction(configuration.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      const response = result.data
      if (response.success) {
        toast.success(response.message ?? 'Connection successful')
      } else {
        toast.error(response.message ?? 'Connection failed')
      }
    } catch (error) {
      console.error('[StorageConfigurationManager] Failed to test storage configuration', error)
      toast.error('Unable to test storage configuration')
    } finally {
      setTestingId(null)
    }
  }

  const handleDeleteConfiguration = async (
    configuration: StorageConfiguration,
    hasUsage: boolean,
    force = false,
  ) => {
    if (requireMaintenance()) {
      return
    }
    if (hasUsage && !isMaintenanceActive && !force) {
      toast.error('Enable maintenance mode before deleting a storage backend in use.')
      return
    }
    setDeletingId(configuration.id)
    try {
      const result = await deleteStorageConfigurationAction(configuration.id, force)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      if (force) {
        queryClient.setQueryData<StorageConfigurationListResponse>(
          queryKeys.storageConfigurations(STORAGE_QUERY_PARAMS),
          (current) =>
            current === undefined
              ? current
              : {
                  ...current,
                  data: current.data.filter((entry) => entry.id !== configuration.id),
                  total: Math.max(current.total - 1, 0),
                },
        )
        queryClient.setQueryData<StorageOverviewResponse>(
          queryKeys.storageOverview(),
          (current) =>
            current === undefined ? current : removeOverviewConfiguration(current, configuration.id),
        )
      } else {
        const disabledConfiguration = { ...configuration, enabled: false }
        queryClient.setQueryData<StorageConfigurationListResponse>(
          queryKeys.storageConfigurations(STORAGE_QUERY_PARAMS),
          (current) =>
            current === undefined
              ? current
              : {
                  ...current,
                  data: current.data.map((entry) =>
                    entry.id === configuration.id ? disabledConfiguration : entry,
                  ),
                },
        )
        queryClient.setQueryData<StorageOverviewResponse>(
          queryKeys.storageOverview(),
          (current) =>
            current === undefined
              ? current
              : upsertOverviewConfiguration(current, disabledConfiguration),
        )
      }
      toast.success(force ? 'Configuration deleted' : 'Configuration disabled')
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.storageConfigurationsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.storageOverview() }),
      ])
    } catch (error) {
      console.error('[StorageConfigurationManager] Failed to delete configuration', error)
      toast.error('Unable to delete configuration')
    } finally {
      setDeletingId(null)
    }
  }

  const handleBulkToggle = async (enabled: boolean) => {
    setBulkAction(enabled ? 'enable' : 'disable')
    try {
      for (const configurationId of selectedIds) {
        const configuration = configurations.find((item) => item.id === configurationId)
        if (!configuration) {
          continue
        }
        const usage = overviewMap.get(configuration.id)?.usage?.total_files ?? 0
        await updateConfigurationEnabled(configuration, enabled, usage > 0)
      }
      toast.success(`Updated ${selectedIds.length} configuration${selectedIds.length === 1 ? '' : 's'}`)
      setSelectedIds([])
    } finally {
      setBulkAction(null)
    }
  }

  const handleBulkDelete = async () => {
    setBulkAction('delete')
    try {
      for (const configurationId of selectedIds) {
        const configuration = configurations.find((item) => item.id === configurationId)
        if (!configuration) {
          continue
        }
        const usage = overviewMap.get(configuration.id)?.usage?.total_files ?? 0
        await handleDeleteConfiguration(configuration, usage > 0)
      }
      setSelectedIds([])
    } finally {
      setBulkAction(null)
    }
  }

  const handleMaintenanceConfirm = async () => {
    if (!pendingCreate) {
      setMaintenanceModalOpen(false)
      return
    }
    await submitConfiguration(pendingCreate)
    setPendingCreate(null)
    setMaintenanceModalOpen(false)
  }

  const hasConfigurations = configurations.length > 0

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-lg font-semibold">Storage Platform</h2>
          <p className="text-sm text-muted-foreground">
            Manage where PDFs, exports, and raw source files are stored.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>Add Configuration</Button>
      </div>

      {resolvedOverview ? (
        <StorageOverviewSection overview={resolvedOverview} showBeta={showDashboardBeta} />
      ) : null}

      {configurationResponse === null ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : hasConfigurations ? (
        <div className="space-y-4">
          {configurations.map((configuration) => (
            <StorageConfigurationCard
              key={configuration.id}
              configuration={configuration}
              usage={overviewMap.get(configuration.id)?.usage ?? null}
              health={overviewMap.get(configuration.id)?.health ?? null}
              onToggleEnabled={updateConfigurationEnabled}
              onTestConnection={handleTestConnection}
              isTesting={testingId === configuration.id}
              isToggling={togglingId === configuration.id}
              isSelected={selectedSet.has(configuration.id)}
              onSelectionChange={(id, selected) => {
                setSelectedIds((current) =>
                  selected ? [...new Set([...current, id])] : current.filter((item) => item !== id),
                )
              }}
              onDelete={handleDeleteConfiguration}
              isDeleting={deletingId === configuration.id}
              enableSelection={showDashboardBeta}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
            <AlertCircle className="size-4" />
            No storage configurations found. Create one to begin storing artifacts.
          </CardContent>
        </Card>
      )}

      <BulkActionBar
        count={selectedIds.length}
        onClear={() => setSelectedIds([])}
        onEnable={() => handleBulkToggle(true)}
        onDisable={() => handleBulkToggle(false)}
        onDelete={handleBulkDelete}
        isProcessing={bulkAction !== null}
        showBeta={showDashboardBeta}
      />

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>New Storage Configuration</DialogTitle>
            <DialogDescription>
              Define a storage backend for PDFs, exports, and ingestion payloads.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Cloud Archive" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="provider"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Provider</FormLabel>
                      <FormControl>
                        <select
                          {...field}
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
                        >
                          {STORAGE_PROVIDERS.map((provider) => (
                            <option key={provider} value={provider}>
                              {providerLabels[provider]}
                            </option>
                          ))}
                        </select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {selectedProvider === 'local_filesystem' ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="base_path"
                    render={({ field }) => (
                      <FormItem className="md:col-span-2">
                        <FormLabel>Base Path</FormLabel>
                        <FormControl>
                          <Input placeholder="/var/artana/storage" {...field} />
                        </FormControl>
                        <FormDescription>Directory where files will be stored.</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="create_directories"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-md border p-3">
                        <div>
                          <FormLabel>Create directories</FormLabel>
                          <FormDescription>Automatically create missing directories.</FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="expose_file_urls"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-md border p-3">
                        <div>
                          <FormLabel>Expose file URLs</FormLabel>
                          <FormDescription>
                            Generate file:// URLs for debugging. Not recommended for production.
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              ) : (
                <div className="grid gap-4">
                  <FormField
                    control={form.control}
                    name="bucket_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Bucket Name</FormLabel>
                        <FormControl>
                          <Input placeholder="artana-storage" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="base_path"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Path Prefix</FormLabel>
                          <FormControl>
                            <Input placeholder="/pubmed" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="credentials_secret_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Credentials Secret</FormLabel>
                          <FormControl>
                            <Input placeholder="projects/.../secrets/artana" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="public_read"
                      render={({ field }) => (
                        <FormItem className="flex items-center justify-between rounded-md border p-3">
                          <div>
                            <FormLabel>Public Read</FormLabel>
                            <FormDescription>Allow unsigned public downloads.</FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="signed_url_ttl_seconds"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Signed URL TTL (seconds)</FormLabel>
                          <FormControl>
                            <Input type="number" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              )}

              <Separator />

              <FormField
                control={form.control}
                name="default_use_cases"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default Use Cases</FormLabel>
                    <div className="flex flex-wrap gap-2">
                      {STORAGE_USE_CASES.map((useCase) => {
                        const selected = field.value.includes(useCase)
                        return (
                          <Button
                            key={useCase}
                            type="button"
                            size="sm"
                            variant={selected ? 'default' : 'outline'}
                            onClick={() => {
                              const next = selected
                                ? field.value.filter((item) => item !== useCase)
                                : [...field.value, useCase]
                              field.onChange(next)
                            }}
                          >
                            {useCaseLabels[useCase]}
                          </Button>
                        )
                      })}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating && (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  )}
                  Create Configuration
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      <Dialog open={maintenanceModalOpen} onOpenChange={setMaintenanceModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable maintenance mode first</DialogTitle>
            <DialogDescription>
              At least one storage backend is currently enabled. Enable maintenance mode to log out
              users and prevent writes before changing the provider or base path.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setPendingCreate(null)
                setMaintenanceModalOpen(false)
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleMaintenanceConfirm}>
              Continue without maintenance
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

function convertFormToPayload(values: StorageFormValues): CreateStorageConfigurationRequest {
  const common = {
    name: values.name.trim(),
    provider: values.provider,
    default_use_cases: values.default_use_cases,
    enabled: values.enabled,
  }

  if (values.provider === 'local_filesystem') {
    return {
      ...common,
      config: {
        provider: 'local_filesystem',
        base_path: values.base_path,
        create_directories: values.create_directories,
        expose_file_urls: values.expose_file_urls,
      } satisfies StorageProviderConfig,
    }
  }

  return {
    ...common,
    config: {
      provider: 'google_cloud_storage',
      bucket_name: values.bucket_name,
      base_path: values.base_path,
      credentials_secret_name: values.credentials_secret_name,
      public_read: values.public_read,
      signed_url_ttl_seconds: values.signed_url_ttl_seconds,
    } satisfies StorageProviderConfig,
  }
}
