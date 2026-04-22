"use server"

import { revalidatePath } from 'next/cache'

import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'
import {
  mergeDictionaryEntityType,
  mergeDictionaryRelationType,
  mergeDictionaryVariable,
  revokeDictionaryEntityType,
  revokeDictionaryRelationType,
  revokeDictionaryVariable,
} from '@/lib/api/dictionary'
import type {
  DictionaryEntityTypeResponse,
  DictionaryRelationTypeResponse,
  VariableDefinitionResponse,
} from '@/types/dictionary'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateDictionary() {
  revalidatePath('/admin/dictionary')
}

export async function revokeVariableAction(
  variableId: string,
  reason: string,
): Promise<ActionResult<VariableDefinitionResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await revokeDictionaryVariable(variableId, { reason }, token)
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] revokeVariableAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to revoke variable'),
    }
  }
}

export async function mergeVariableAction(
  variableId: string,
  targetId: string,
  reason: string,
): Promise<ActionResult<VariableDefinitionResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await mergeDictionaryVariable(
      variableId,
      { target_id: targetId, reason },
      token,
    )
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] mergeVariableAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to merge variable'),
    }
  }
}

export async function revokeEntityTypeAction(
  entityTypeId: string,
  reason: string,
): Promise<ActionResult<DictionaryEntityTypeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await revokeDictionaryEntityType(entityTypeId, { reason }, token)
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] revokeEntityTypeAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to revoke entity type'),
    }
  }
}

export async function mergeEntityTypeAction(
  entityTypeId: string,
  targetId: string,
  reason: string,
): Promise<ActionResult<DictionaryEntityTypeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await mergeDictionaryEntityType(
      entityTypeId,
      { target_id: targetId, reason },
      token,
    )
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] mergeEntityTypeAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to merge entity type'),
    }
  }
}

export async function revokeRelationTypeAction(
  relationTypeId: string,
  reason: string,
): Promise<ActionResult<DictionaryRelationTypeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await revokeDictionaryRelationType(relationTypeId, { reason }, token)
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] revokeRelationTypeAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to revoke relation type'),
    }
  }
}

export async function mergeRelationTypeAction(
  relationTypeId: string,
  targetId: string,
  reason: string,
): Promise<ActionResult<DictionaryRelationTypeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await mergeDictionaryRelationType(
      relationTypeId,
      { target_id: targetId, reason },
      token,
    )
    revalidateDictionary()
    return { success: true, data: response }
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] mergeRelationTypeAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to merge relation type'),
    }
  }
}
