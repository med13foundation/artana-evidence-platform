"use server"

import { revalidatePath } from 'next/cache'
import {
  activateUser,
  createUser,
  deleteUser,
  lockUser,
  unlockUser,
  updateUser,
} from '@/lib/api/users'
import type {
  CreateUserRequest,
  UpdateUserRequest,
  UserProfileResponse,
  GenericSuccessResponse,
} from '@/lib/api/users'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateUsers() {
  revalidatePath('/system-settings')
  revalidatePath('/admin/phi-access')
}

export async function createUserAction(
  payload: CreateUserRequest,
): Promise<ActionResult<UserProfileResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createUser(payload, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create user'),
    }
  }
}

export async function updateUserAction(
  userId: string,
  payload: UpdateUserRequest,
): Promise<ActionResult<UserProfileResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateUser(userId, payload, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update user'),
    }
  }
}

export async function deleteUserAction(
  userId: string,
): Promise<ActionResult<GenericSuccessResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await deleteUser(userId, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete user'),
    }
  }
}

export async function lockUserAction(
  userId: string,
): Promise<ActionResult<GenericSuccessResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await lockUser(userId, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] lockUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to suspend user'),
    }
  }
}

export async function unlockUserAction(
  userId: string,
): Promise<ActionResult<GenericSuccessResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await unlockUser(userId, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] unlockUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to reactivate user'),
    }
  }
}

export async function activateUserAction(
  userId: string,
): Promise<ActionResult<GenericSuccessResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await activateUser(userId, token)
    revalidateUsers()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] activateUser failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to activate user'),
    }
  }
}
