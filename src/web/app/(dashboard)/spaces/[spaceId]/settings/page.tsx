import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { fetchResearchSpace } from '@/lib/api/research-spaces'
import SpaceSettingsClient from '../space-settings-client'

interface SpaceSettingsPageProps {
  params: Promise<{
    spaceId: string
  }>
}

export default async function SpaceSettingsPage({ params }: SpaceSettingsPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let space = null

  try {
    space = await fetchResearchSpace(spaceId, token)
  } catch (error) {
    console.error('[SpaceSettingsPage] Failed to fetch research space', error)
  }
  const effectiveSpaceId = space?.id ?? spaceId

  return <SpaceSettingsClient spaceId={effectiveSpaceId} space={space} />
}
