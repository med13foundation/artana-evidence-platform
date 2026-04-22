import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'

interface SpaceIngestPageProps {
  params: Promise<{ spaceId: string }>
}

export default async function SpaceIngestPage({ params }: SpaceIngestPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  redirect(`/spaces/${spaceId}/data-sources`)
}
