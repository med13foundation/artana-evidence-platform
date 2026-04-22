"use server"

import { revalidatePath } from 'next/cache'
import { createDictionaryVariable } from '@/lib/api/dictionary'
import type { VariableDefinitionCreateRequest, VariableDefinitionResponse } from '@/types/dictionary'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateDictionary() {
  revalidatePath('/admin/dictionary')
}

export async function createDictionaryVariableAction(
  payload: VariableDefinitionCreateRequest,
): Promise<ActionResult<VariableDefinitionResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createDictionaryVariable(payload, token)
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createDictionaryVariable failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create dictionary variable'),
    }
  }
}
