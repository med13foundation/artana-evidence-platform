'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Plus, FolderPlus, Settings } from 'lucide-react'
import { useSpaceContext } from '@/components/space-context-provider'
import { useRouter } from 'next/navigation'
import { DashboardSection, PageHero } from '@/components/ui/composition-patterns'
import { getThemeVariant } from '@/lib/theme/variants'
import { ResearchSpaceCard } from '@/components/research-spaces/ResearchSpaceCard'
import { UserRole } from '@/types/auth'

interface DashboardClientProps {
  userRole: UserRole
}

export default function DashboardClient({ userRole }: DashboardClientProps) {
  const { currentSpaceId, spaces, isLoading: spacesLoading } = useSpaceContext()
  const router = useRouter()
  const theme = getThemeVariant('research')

  const hasSpaces = spaces.length > 0
  const canCreateSpace = userRole === UserRole.ADMIN
  const canAccessSystemSettings = userRole === UserRole.ADMIN
  const currentSpaceName = currentSpaceId
    ? spaces.find((space) => space.id === currentSpaceId)?.name || currentSpaceId
    : null

  return (
    <div className="flex flex-col gap-brand-md sm:gap-brand-lg">
      <PageHero
        eyebrow="Admin"
        title="Admin Console"
        description="Select a research space to manage project-level data. Use system settings for platform-wide controls."
        variant="research"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canAccessSystemSettings && (
              <Button
                variant="outline"
                onClick={() => router.push('/system-settings')}
                className="flex items-center gap-2"
              >
                <Settings className="size-4" />
                <span>System Settings</span>
              </Button>
            )}
            {canCreateSpace && (
              <Button onClick={() => router.push('/spaces/new')} className="flex items-center gap-2">
                <Plus className="size-5" />
                <span>Create Space</span>
              </Button>
            )}
          </div>
        }
      />

      {currentSpaceName && (
        <Card className="border-dashed">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Current space</p>
              <p className="font-medium text-foreground">{currentSpaceName}</p>
            </div>
            <Button variant="secondary" onClick={() => router.push(`/spaces/${currentSpaceId}`)}>
              Open space
            </Button>
          </CardContent>
        </Card>
      )}

      <DashboardSection
        title="Research Spaces"
        description="Spaces you can access. Open a space to see project-specific stats, data sources, and activity."
        className={theme.card}
      >
        {spacesLoading ? (
          <div className="space-y-3 text-sm text-muted-foreground">
            <div className="h-4 w-32 rounded bg-muted" />
            <div className="h-4 w-48 rounded bg-muted" />
            <div className="h-4 w-24 rounded bg-muted" />
          </div>
        ) : hasSpaces ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {spaces.map((space) => (
              <ResearchSpaceCard
                key={space.id}
                space={space}
                onSettings={() => router.push(`/spaces/${space.id}/settings`)}
              />
            ))}
          </div>
        ) : (
          <Card className="border-dashed border-brand-primary/20 bg-brand-primary/5">
            <CardContent className="flex flex-col items-center justify-center px-4 py-16 text-center sm:px-8">
              <div className="mb-6 rounded-full bg-brand-primary/10 p-4 sm:p-6">
                <FolderPlus className="size-8 text-brand-primary sm:size-10" />
              </div>
              <h3 className="mb-2 font-heading text-xl font-bold">No research spaces yet</h3>
              <p className="mb-8 max-w-md text-base text-muted-foreground">
                Create a space to organize research work. Data sources, records, and activity
                will live inside each space.
              </p>
              {canCreateSpace && (
                <Button onClick={() => router.push('/spaces/new')} className="flex items-center gap-2 shadow-brand-md">
                  <Plus className="size-5" />
                  <span>Create your first space</span>
                </Button>
              )}
            </CardContent>
          </Card>
        )}
      </DashboardSection>
    </div>
  )
}
