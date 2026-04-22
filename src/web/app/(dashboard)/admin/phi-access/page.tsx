import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'
import { fetchUsers, type UserListResponse } from '@/lib/api/users'
import { UserRole } from '@/types/auth'

import PhiAccessClient from './phi-access-client'

export default async function PhiAccessPage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard?error=AdminOnly')
  }

  let users: UserListResponse | null = null
  let usersError: string | null = null

  try {
    users = await fetchUsers({ skip: 0, limit: 500 }, token)
  } catch (error) {
    usersError = error instanceof Error ? error.message : 'Unable to load users.'
    console.error('[PhiAccessPage] Failed to load users', error)
  }

  return (
    <PhiAccessClient
      users={users}
      usersError={usersError}
      currentUserId={session.user.id ?? ''}
    />
  )
}
