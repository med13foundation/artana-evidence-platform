import { NextResponse } from 'next/server'

import { getActionErrorMessage, getActionErrorStatus, requireAccessToken } from '@/app/actions/action-utils'
import { getAvailableModels } from '@/lib/api/ai-models'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(): Promise<NextResponse> {
  try {
    const token = await requireAccessToken()
    const response = await getAvailableModels(token)
    return new NextResponse(JSON.stringify(response), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  } catch (error: unknown) {
    const message = getActionErrorMessage(error, 'Failed to load available models')
    const status = getActionErrorStatus(error) ?? (message === 'Session expired' ? 401 : 500)
    return new NextResponse(JSON.stringify({ detail: message }), {
      status,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }
}
