import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { getDefaultPostLoginDestination } from '@/lib/post-login-destination'

export default async function HomePage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  const expiresAt = session?.user?.expires_at
  const isExpired = typeof expiresAt !== 'number' || Date.now() >= expiresAt

  if (!session || !token || isExpired) {
    redirect('/auth/login')
  }

  redirect(getDefaultPostLoginDestination(session.user.role))
}
