'use client'

import { useEffect, useState } from 'react'
import {
  deleteResearchSpaceAction,
  removeMemberAction,
  updateMemberRoleAction,
  updateResearchSpaceAction,
} from '@/app/actions/research-spaces'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SpaceMembersList } from './SpaceMembersList'
import { InviteMemberDialog } from './InviteMemberDialog'
import { Loader2, Settings, Trash2, Users, Database, BarChart3, FileText } from 'lucide-react'
import { SpaceStatus, MembershipRole } from '@/types/research-space'
import type { ResearchSpace, ResearchSpaceMembership } from '@/types/research-space'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { CurationQueueResponse, CurationStats } from '@/lib/api/research-spaces'
import { DashboardSection, SectionGrid, StatCard } from '@/components/ui/composition-patterns'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { toast } from 'sonner'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface ResearchSpaceAccess {
  hasSpaceAccess: boolean
  canManageMembers: boolean
  canEditSpace: boolean
  isOwner: boolean
  showMembershipNotice: boolean
}

interface ResearchSpaceDetailProps {
  spaceId: string
  space: ResearchSpace | null
  memberships: ResearchSpaceMembership[]
  membersError?: string | null
  dataSources: DataSourceListResponse | null
  curationStats: CurationStats | null
  curationQueue: CurationQueueResponse | null
  relationTypeDistribution: Array<{ label: string; count: number }>
  nodeDistribution: Array<{ label: string; count: number }>
  access: ResearchSpaceAccess
  defaultTab?: string
}

const statusColors: Record<SpaceStatus, string> = {
  [SpaceStatus.ACTIVE]: 'bg-green-500',
  [SpaceStatus.INACTIVE]: 'bg-gray-500',
  [SpaceStatus.ARCHIVED]: 'bg-yellow-500',
  [SpaceStatus.SUSPENDED]: 'bg-red-500',
}

const statusLabels: Record<SpaceStatus, string> = {
  [SpaceStatus.ACTIVE]: 'Active',
  [SpaceStatus.INACTIVE]: 'Inactive',
  [SpaceStatus.ARCHIVED]: 'Archived',
  [SpaceStatus.SUSPENDED]: 'Suspended',
}

export function ResearchSpaceDetail({
  spaceId,
  space,
  memberships,
  membersError,
  dataSources,
  curationStats,
  curationQueue,
  relationTypeDistribution,
  nodeDistribution,
  access,
  defaultTab = 'overview',
}: ResearchSpaceDetailProps) {
  const router = useRouter()
  const spaceData = space
  const dataSourcesResponse = dataSources ?? null
  const totalDataSources = dataSourcesResponse?.total ?? 0
  const recentSources = dataSourcesResponse?.items ?? []
  const curationQueueData = curationQueue ?? null
  const showOnboarding = access.hasSpaceAccess && totalDataSources === 0
  const hasDataSources = access.hasSpaceAccess && totalDataSources > 0
  const dataSourceStatusCounts = recentSources.reduce<Record<string, number>>((acc, source) => {
    const status = source.status || 'unknown'
    acc[status] = (acc[status] ?? 0) + 1
    return acc
  }, {})
  const curationTotal = curationStats?.total ?? 0
  const pendingCount = curationStats?.pending ?? 0
  const approvedCount = curationStats?.approved ?? 0
  const rejectedCount = curationStats?.rejected ?? 0
  const curatedCount = approvedCount + rejectedCount
  const notCuratedCount = Math.max(curationTotal - curatedCount, pendingCount)
  const completionRate =
    curationTotal > 0 ? Math.round((curatedCount / curationTotal) * 100) : 0
  const statusAreaData = [
    { label: 'Pending', value: pendingCount },
    { label: 'Approved', value: approvedCount },
    { label: 'Rejected', value: rejectedCount },
  ]
  const curationBalanceData = [
    { label: 'Curated', value: curatedCount, fill: 'hsl(var(--chart-1))' },
    { label: 'Not Curated', value: notCuratedCount, fill: 'hsl(var(--chart-2))' },
  ]

  const [inviteDialogOpen, setInviteDialogOpen] = useState(false)
  const [pendingMembershipId, setPendingMembershipId] = useState<string | null>(null)
  const [isDeletingSpace, setIsDeletingSpace] = useState(false)

  const [membershipList, setMembershipList] = useState<ResearchSpaceMembership[]>(memberships)
  const canManage = access.canManageMembers
  const isOwner = access.isOwner
  const canEditSpace = access.canEditSpace
  const showMembershipNotice = access.showMembershipNotice

  useEffect(() => {
    setMembershipList(memberships)
  }, [memberships])

  const handleUpdateRole = async (membershipId: string, nextRole: MembershipRole) => {
    const currentMembership = membershipList.find((membership) => membership.id === membershipId)
    if (!currentMembership || currentMembership.role === nextRole) {
      return
    }

    try {
      setPendingMembershipId(membershipId)
      const result = await updateMemberRoleAction(spaceId, membershipId, {
        role: nextRole,
      })
      if (!result.success) {
        toast.error(result.error)
        return
      }

      setMembershipList((prev) =>
        prev.map((membership) =>
          membership.id === membershipId ? result.data : membership,
        ),
      )
      toast.success('Member role updated')
      router.refresh()
    } catch (error) {
      console.error('Failed to update role:', error)
      toast.error('Failed to update role')
    } finally {
      setPendingMembershipId(null)
    }
  }

  const handleRemoveMember = async (membershipId: string) => {
    if (confirm('Are you sure you want to remove this member?')) {
      try {
        setPendingMembershipId(membershipId)
        const result = await removeMemberAction(spaceId, membershipId)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        setMembershipList((prev) => prev.filter((membership) => membership.id !== membershipId))
        toast.success('Member removed')
        router.refresh()
      } catch (error) {
        console.error('Failed to remove member:', error)
        toast.error('Failed to remove member')
      } finally {
        setPendingMembershipId(null)
      }
    }
  }

  const handleDeleteSpace = async () => {
    if (confirm('Are you sure you want to delete this space? This action cannot be undone.')) {
      try {
        setIsDeletingSpace(true)
        const result = await deleteResearchSpaceAction(spaceId)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success('Space deleted')
        router.push('/dashboard')
      } catch (error) {
        console.error('Failed to delete space:', error)
        toast.error('Failed to delete space')
      } finally {
        setIsDeletingSpace(false)
      }
    }
  }

  if (!spaceData) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
        <p className="text-sm text-destructive">Research space not found</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <h1 className="font-heading text-3xl font-bold tracking-tight">{spaceData.name}</h1>
            <Badge
              className={cn(
                statusColors[spaceData.status],
                'text-white'
              )}
            >
              {statusLabels[spaceData.status]}
            </Badge>
          </div>
          <p className="mt-1 font-mono text-sm text-muted-foreground">{spaceData.slug}</p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Settings className="mr-2 size-4" />
              Settings
            </Button>
            {isOwner && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteSpace}
                disabled={isDeletingSpace}
              >
                <Trash2 className="mr-2 size-4" />
                Delete
              </Button>
            )}
          </div>
        )}
      </div>

      <Tabs defaultValue={defaultTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="members">
            <Users className="mr-2 size-4" />
            Members
          </TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <SpaceDescriptionCard
            spaceId={spaceId}
            description={spaceData.description}
            canEdit={canEditSpace}
          />

          {showMembershipNotice && (
            <Alert>
              <AlertTitle>Limited access</AlertTitle>
              <AlertDescription>
                You are not a member of this research space. Ask an owner to invite you to view
                curation activity or edit settings.
              </AlertDescription>
            </Alert>
          )}

          {showOnboarding && (
            <Card className="border-dashed bg-card/80">
              <CardHeader>
                <CardTitle>Welcome to your new research space</CardTitle>
                <CardDescription>
                  Set up your data sources and curation workflow. This view will turn into a space
                  dashboard once data starts flowing.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border p-3">
                    <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <Database className="size-4 text-muted-foreground" />
                      Add data sources
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Connect APIs or uploads to start ingesting research data.
                    </p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <FileText className="size-4 text-muted-foreground" />
                      Curate and review
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Validate incoming records and track review status.
                    </p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <BarChart3 className="size-4 text-muted-foreground" />
                      Explore the graph
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Visualize genes, variants, and evidence once data is ready.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Button onClick={() => router.push(`/spaces/${spaceId}/data-sources`)}>
                    Configure data sources
                  </Button>
                  <Button variant="outline" onClick={() => router.push(`/spaces/${spaceId}/curation`)}>
                    Start curation
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => router.push(`/spaces/${spaceId}/knowledge-graph`)}
                  >
                    Explore graph
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {hasDataSources && (
            <>
              <SectionGrid>
                <StatCard
                  title="Data Sources"
                  value={totalDataSources}
                  description={`Active ${dataSourceStatusCounts['active'] ?? 0} • Pending ${dataSourceStatusCounts['pending_review'] ?? 0}`}
                  icon={<Database className="size-4 text-muted-foreground" />}
                  isLoading={false}
                />
                <StatCard
                  title="Pending Curation"
                  value={curationStats?.pending ?? 0}
                  description={`Approved ${curationStats?.approved ?? 0} • Rejected ${curationStats?.rejected ?? 0}`}
                  icon={<FileText className="size-4 text-muted-foreground" />}
                  isLoading={false}
                />
                <StatCard
                  title="Total Records"
                  value={(curationStats?.total ?? 0) + totalDataSources}
                  description="Curation items + data sources"
                  icon={<BarChart3 className="size-4 text-muted-foreground" />}
                  isLoading={false}
                />
              </SectionGrid>

              <DashboardSection
                title="Recent Data Sources"
                description="Latest sources configured in this space"
              >
                <div className="space-y-3">
                  {recentSources.map((source) => (
                    <div
                      key={source.id}
                      className="flex flex-col gap-1 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="text-sm font-semibold text-foreground">{source.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {source.source_type} • Status: {source.status}
                        </p>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Last updated {source.updated_at ? new Date(source.updated_at).toLocaleString() : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </DashboardSection>

              <DashboardSection
                title="Curation Health"
                description="Curated vs not-curated balance and status distribution"
              >
                <div className="grid gap-4 lg:grid-cols-3">
                  <Card className="lg:col-span-2">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Status Distribution</CardTitle>
                      <CardDescription>Pending, approved, and rejected records</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="h-56 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={statusAreaData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                            <defs>
                              <linearGradient id="statusAreaFill" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(var(--chart-1))" stopOpacity={0.55} />
                                <stop offset="95%" stopColor="hsl(var(--chart-1))" stopOpacity={0.08} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
                            <RechartsTooltip />
                            <Area
                              type="monotone"
                              dataKey="value"
                              stroke="hsl(var(--chart-1))"
                              strokeWidth={2}
                              fill="url(#statusAreaFill)"
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Curation Balance</CardTitle>
                      <CardDescription>Curated records vs backlog</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="mx-auto h-44 w-full max-w-[230px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={curationBalanceData}
                              dataKey="value"
                              nameKey="label"
                              innerRadius={48}
                              outerRadius={76}
                              paddingAngle={3}
                            >
                              {curationBalanceData.map((entry) => (
                                <Cell key={entry.label} fill={entry.fill} />
                              ))}
                            </Pie>
                            <RechartsTooltip />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>

                      <div className="space-y-2 text-sm">
                        <div className="flex items-center justify-between rounded-md border px-3 py-2">
                          <span className="text-muted-foreground">Curated</span>
                          <span className="font-semibold text-foreground">{curatedCount}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-md border px-3 py-2">
                          <span className="text-muted-foreground">Not curated</span>
                          <span className="font-semibold text-foreground">{notCuratedCount}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-md border px-3 py-2">
                          <span className="text-muted-foreground">Completion</span>
                          <span className="font-semibold text-foreground">{completionRate}%</span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Relation Type Distribution</CardTitle>
                      <CardDescription>Most frequent relation types in this space</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {relationTypeDistribution.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No relation-type data available yet.</p>
                      ) : (
                        <div className="h-64 w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              data={relationTypeDistribution}
                              layout="vertical"
                              margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                              <XAxis
                                type="number"
                                allowDecimals={false}
                                tickLine={false}
                                axisLine={false}
                                fontSize={12}
                              />
                              <YAxis
                                type="category"
                                dataKey="label"
                                width={150}
                                tickLine={false}
                                axisLine={false}
                                fontSize={11}
                              />
                              <RechartsTooltip />
                              <Bar dataKey="count" fill="hsl(var(--chart-4))" radius={[0, 6, 6, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Node Distribution</CardTitle>
                      <CardDescription>Most connected nodes in current relation graph</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {nodeDistribution.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No node-distribution data available yet.</p>
                      ) : (
                        <div className="h-64 w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              data={nodeDistribution}
                              layout="vertical"
                              margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                              <XAxis
                                type="number"
                                allowDecimals={false}
                                tickLine={false}
                                axisLine={false}
                                fontSize={12}
                              />
                              <YAxis
                                type="category"
                                dataKey="label"
                                width={150}
                                tickLine={false}
                                axisLine={false}
                                fontSize={11}
                              />
                              <RechartsTooltip />
                              <Bar dataKey="count" fill="hsl(var(--chart-5))" radius={[0, 6, 6, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </DashboardSection>

              <DashboardSection
                title="Activity Feed"
                description="Latest curation queue activity for this space"
              >
                {(curationQueueData?.items.length ?? 0) === 0 ? (
                  <p className="text-sm text-muted-foreground">No recent activity yet.</p>
                ) : (
                  <div className="space-y-3">
                    {curationQueueData?.items.map((item) => (
                      <div
                        key={item.id}
                        className="flex flex-col gap-1 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            {item.entity_type} #{item.entity_id}
                          </p>
                          <p className="text-xs text-muted-foreground">Status: {item.status}</p>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Updated {item.last_updated ? new Date(item.last_updated).toLocaleString() : '—'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </DashboardSection>
            </>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Space Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Created</p>
                <p>{new Date(spaceData.created_at).toLocaleDateString()}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Last Updated</p>
                <p>{new Date(spaceData.updated_at).toLocaleDateString()}</p>
              </div>
              {spaceData.tags.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium text-muted-foreground">Tags</p>
                  <div className="flex flex-wrap gap-2">
                    {spaceData.tags.map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="members" className="space-y-4">
          <SpaceMembersList
            memberships={membershipList}
            isLoading={false}
            errorMessage={membersError ?? null}
            onInvite={() => setInviteDialogOpen(true)}
            onUpdateRole={handleUpdateRole}
            onRemove={handleRemoveMember}
            canManage={canManage}
            pendingMembershipId={pendingMembershipId}
          />
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Space Settings</CardTitle>
              <CardDescription>Manage space configuration and preferences</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">Settings coming soon...</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <InviteMemberDialog
        spaceId={spaceId}
        open={inviteDialogOpen}
        setDialogOpen={setInviteDialogOpen}
        afterInvite={() => router.refresh()}
      />
    </div>
  )
}

interface SpaceDescriptionCardProps {
  spaceId: string
  description?: string | null
  canEdit: boolean
}

function SpaceDescriptionCard({ spaceId, description, canEdit }: SpaceDescriptionCardProps) {
  const router = useRouter()
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState<string>(description ?? '')
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    setDraft(description ?? '')
  }, [description])

  const initialDescription = description ?? ''
  const hasChanges = draft !== initialDescription
  const displayDescription =
    initialDescription.trim() === '' ? 'No description provided yet.' : initialDescription

  const handleSave = async () => {
    if (!canEdit) {
      toast.error('Only the space owner can edit the description.')
      return
    }

    if (!hasChanges) {
      setIsEditing(false)
      return
    }

    try {
      setIsSaving(true)
      const result = await updateResearchSpaceAction(spaceId, { description: draft })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success('Description updated')
      setIsEditing(false)
      router.refresh()
    } catch (error) {
      console.error('Failed to update description', error)
      toast.error('Unable to update description. Please try again.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setDraft(initialDescription)
    setIsEditing(false)
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Project description</CardTitle>
          <CardDescription>Give collaborators context for this research space.</CardDescription>
        </div>
        {canEdit && !isEditing ? (
          <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
            Edit description
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {isEditing ? (
          <>
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={4}
              maxLength={500}
              placeholder="Describe the goals, scope, and data being curated in this space."
              disabled={isSaving}
            />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                Save description
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCancel}
                disabled={isSaving}
              >
                Cancel
              </Button>
            </div>
          </>
        ) : (
          <p className="whitespace-pre-wrap text-sm text-foreground">{displayDescription}</p>
        )}
      </CardContent>
    </Card>
  )
}
