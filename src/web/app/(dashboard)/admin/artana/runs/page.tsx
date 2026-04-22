import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import AdminArtanaRunsClient from '@/app/(dashboard)/admin/artana/runs/admin-artana-runs-client'
import { fetchAdminArtanaRunTrace, fetchAdminArtanaRuns } from '@/lib/api/artana'
import { authOptions } from '@/lib/auth'
import { UserRole } from '@/types/auth'
import type {
  ArtanaRunListParams,
  ArtanaRunListResponse,
  ArtanaRunTraceResponse,
} from '@/types/artana'

interface AdminArtanaRunsPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function readSingleParam(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0]
  }
  return value
}

function parsePositiveInt(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export default async function AdminArtanaRunsPage({
  searchParams,
}: AdminArtanaRunsPageProps) {
  const resolvedSearchParams = await searchParams
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard?error=AdminOnly')
  }

  const selectedRunId = readSingleParam(resolvedSearchParams.run_id)
  const filters: ArtanaRunListParams = {
    q: readSingleParam(resolvedSearchParams.q),
    status: readSingleParam(resolvedSearchParams.status),
    space_id: readSingleParam(resolvedSearchParams.space_id),
    source_type: readSingleParam(resolvedSearchParams.source_type),
    alert_code: readSingleParam(resolvedSearchParams.alert_code),
    since_hours: (() => {
      const raw = readSingleParam(resolvedSearchParams.since_hours)
      if (!raw) {
        return undefined
      }
      const parsed = Number.parseInt(raw, 10)
      return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
    })(),
    page: parsePositiveInt(readSingleParam(resolvedSearchParams.page), 1),
    per_page: parsePositiveInt(readSingleParam(resolvedSearchParams.per_page), 25),
  }

  let runs: ArtanaRunListResponse | null = null
  let runsError: string | null = null
  let trace: ArtanaRunTraceResponse | null = null
  let traceError: string | null = null

  try {
    runs = await fetchAdminArtanaRuns(filters, token)
  } catch (error) {
    runsError = error instanceof Error ? error.message : 'Unable to load Artana runs.'
  }

  if (selectedRunId) {
    try {
      trace = await fetchAdminArtanaRunTrace(selectedRunId, token)
    } catch (error) {
      traceError = error instanceof Error ? error.message : 'Unable to load Artana run detail.'
    }
  }

  return (
    <AdminArtanaRunsClient
      filters={filters}
      selectedRunId={selectedRunId}
      runs={runs}
      runsError={runsError}
      trace={trace}
      traceError={traceError}
    />
  )
}
