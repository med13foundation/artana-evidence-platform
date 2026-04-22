import { ResearchSpacesList } from '@/components/research-spaces/ResearchSpacesList'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { fetchResearchSpaces } from '@/lib/api/research-spaces'
import { redirect } from 'next/navigation'
import type { ResearchSpace } from '@/types/research-space'

function normalizeSpaces(value: unknown): ResearchSpace[] {
  return Array.isArray(value) ? (value as ResearchSpace[]) : []
}

export default async function SpacesIndexPage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect("/auth/login?error=SessionExpired")
  }

  let initialSpaces: Awaited<ReturnType<typeof fetchResearchSpaces>>['spaces'] = []
  let initialTotal = 0
  let errorMessage: string | null = null

  try {
    const response = await fetchResearchSpaces(undefined, token)
    initialSpaces = normalizeSpaces(response.spaces)
    initialTotal = typeof response.total === 'number' ? response.total : initialSpaces.length
  } catch (error) {
    console.error('[SpacesIndexPage] Failed to fetch research spaces', error)
    errorMessage =
      error instanceof Error ? error.message : 'Unable to load research spaces right now.'
  }

  return (
    <ResearchSpacesList
      spaces={initialSpaces}
      total={initialTotal}
      errorMessage={errorMessage}
    />
  )
}
