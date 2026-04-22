"use server"

import { revalidatePath } from 'next/cache'
import {
  createResearchSpace,
  deleteResearchSpace,
  inviteMember,
  removeMember,
  searchInvitableUsers,
  updateMemberRole,
  updateResearchSpace,
} from '@/lib/api/research-spaces'
import type {
  CreateSpaceRequest,
  InvitableUserSearchResponse,
  InviteMemberRequest,
  ResearchSpace,
  ResearchSpaceMembership,
  UpdateMemberRoleRequest,
  UpdateSpaceRequest,
} from '@/types/research-space'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidatePaths(paths: string[]) {
  paths.forEach((path) => revalidatePath(path))
}

export async function createResearchSpaceAction(
  payload: CreateSpaceRequest,
): Promise<ActionResult<ResearchSpace>> {
  try {
    const token = await requireAccessToken()
    const space = await createResearchSpace(payload, token)
    revalidatePaths(['/spaces', '/dashboard'])
    return { success: true, data: space }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createResearchSpace failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create research space'),
    }
  }
}

export async function updateResearchSpaceAction(
  spaceId: string,
  payload: UpdateSpaceRequest,
): Promise<ActionResult<ResearchSpace>> {
  try {
    const token = await requireAccessToken()
    const space = await updateResearchSpace(spaceId, payload, token)
    revalidatePaths([
      `/spaces/${spaceId}`,
      `/spaces/${spaceId}/members`,
      `/spaces/${spaceId}/settings`,
      '/spaces',
      '/dashboard',
    ])
    return { success: true, data: space }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateResearchSpace failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update research space'),
    }
  }
}

export async function deleteResearchSpaceAction(
  spaceId: string,
): Promise<ActionResult<{ id: string }>> {
  try {
    const token = await requireAccessToken()
    await deleteResearchSpace(spaceId, token)
    revalidatePaths(['/spaces', '/dashboard'])
    return { success: true, data: { id: spaceId } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteResearchSpace failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete research space'),
    }
  }
}

export async function inviteMemberAction(
  spaceId: string,
  payload: InviteMemberRequest,
): Promise<ActionResult<ResearchSpaceMembership>> {
  try {
    const token = await requireAccessToken()
    const membership = await inviteMember(spaceId, payload, token)
    revalidatePaths([`/spaces/${spaceId}`, `/spaces/${spaceId}/members`])
    return { success: true, data: membership }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] inviteMember failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to invite member'),
    }
  }
}

export async function searchInvitableUsersAction(
  spaceId: string,
  query: string,
): Promise<ActionResult<InvitableUserSearchResponse>> {
  try {
    const token = await requireAccessToken()
    const results = await searchInvitableUsers(
      spaceId,
      {
        query,
        limit: 8,
      },
      token,
    )
    return { success: true, data: results }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] searchInvitableUsers failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to search users'),
    }
  }
}

export async function updateMemberRoleAction(
  spaceId: string,
  membershipId: string,
  payload: UpdateMemberRoleRequest,
): Promise<ActionResult<ResearchSpaceMembership>> {
  try {
    const token = await requireAccessToken()
    const membership = await updateMemberRole(spaceId, membershipId, payload, token)
    revalidatePaths([`/spaces/${spaceId}`, `/spaces/${spaceId}/members`])
    return { success: true, data: membership }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateMemberRole failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update member role'),
    }
  }
}

export async function removeMemberAction(
  spaceId: string,
  membershipId: string,
): Promise<ActionResult<{ id: string }>> {
  try {
    const token = await requireAccessToken()
    await removeMember(spaceId, membershipId, token)
    revalidatePaths([`/spaces/${spaceId}`, `/spaces/${spaceId}/members`])
    return { success: true, data: { id: membershipId } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] removeMember failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to remove member'),
    }
  }
}
