import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { fetchTemplates } from '@/lib/api/templates'
import TemplatesClient from './templates-client'
import type { TemplateResponse, TemplateScope } from '@/types/template'

export default async function TemplatesPage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  const scopes: TemplateScope[] = ['available', 'public', 'mine']
  const templatesByScope: Record<TemplateScope, TemplateResponse[]> = {
    available: [],
    public: [],
    mine: [],
  }
  const errorsByScope: Record<TemplateScope, string | null> = {
    available: null,
    public: null,
    mine: null,
  }

  await Promise.all(
    scopes.map(async (scope) => {
      try {
        const response = await fetchTemplates(scope, token)
        templatesByScope[scope] = response.templates
      } catch (error) {
        console.error(`[TemplatesPage] Failed to fetch ${scope} templates:`, error)
        errorsByScope[scope] = 'Unable to load templates.'
      }
    }),
  )

  return (
    <TemplatesClient
      templatesByScope={templatesByScope}
      errorsByScope={errorsByScope}
    />
  )
}
