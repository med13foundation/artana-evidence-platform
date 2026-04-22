import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { apiClient, authHeaders } from '@/lib/api/client'
import { authOptions } from '@/lib/auth'
import { buildPlaywrightSession, isPlaywrightE2EMode } from '@/lib/e2e/playwright-auth'
import { getPlaywrightDataDiscoveryPageData } from '@/lib/e2e/playwright-fixtures'
import { fetchSessionState } from '@/app/actions/data-discovery'
import type {
  DataDiscoverySessionResponse,
  OrchestratedSessionState,
  SourceCatalogEntry,
} from '@/types/generated'
import DataDiscoveryClient from './data-discovery-client'

async function ensureSession(token: string): Promise<DataDiscoverySessionResponse> {
  const { data: sessions } = await apiClient.get<DataDiscoverySessionResponse[]>(
    '/data-discovery/sessions',
    authHeaders(token),
  )

  if (sessions.length > 0) {
    return sessions[0]
  }

  const { data: created } = await apiClient.post<DataDiscoverySessionResponse>(
    '/data-discovery/sessions',
    { name: 'Default session' },
    authHeaders(token),
  )
  return created
}

async function fetchCatalog(token: string): Promise<SourceCatalogEntry[]> {
  const { data } = await apiClient.get<SourceCatalogEntry[]>(
    '/data-discovery/catalog',
    authHeaders(token),
  )
  return data
}

export default async function DataDiscoveryPage() {
  if (isPlaywrightE2EMode()) {
    const { orchestratedState, catalog } = getPlaywrightDataDiscoveryPageData()
    return <DataDiscoveryClient orchestratedState={orchestratedState} catalog={catalog} />
  }

  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!token) {
    redirect('/auth/login?error=SessionExpired')
  }

  const baseSession = await ensureSession(token)
  const orchestratedState: OrchestratedSessionState = await fetchSessionState(baseSession.id)
  const catalog = await fetchCatalog(token)

  return <DataDiscoveryClient orchestratedState={orchestratedState} catalog={catalog} />
}
