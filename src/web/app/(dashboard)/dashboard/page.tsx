import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import DashboardClient from './dashboard-client'
import { UserRole } from '@/types/auth'

export default async function DashboardPage() {
  const session = await getServerSession(authOptions)

  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/spaces?error=AdminOnly')
  }

  return <DashboardClient userRole={session.user.role} />
}
