import axios from 'axios'
import { apiGet, apiPost, apiPut, apiDelete, type ApiRequestOptions } from '@/lib/api/client'

export interface UserPublic {
  id: string
  email: string
  username: string
  full_name: string
  role: 'admin' | 'curator' | 'researcher' | 'viewer'
  status: 'active' | 'inactive' | 'suspended' | 'pending_verification'
  email_verified: boolean
  last_login: string | null
  created_at: string
}

export interface UserListResponse {
  users: UserPublic[]
  total: number
  skip: number
  limit: number
}

export interface CreateUserRequest {
  email: string
  username: string
  full_name: string
  password: string
  role: 'admin' | 'curator' | 'researcher' | 'viewer'
}

export interface UpdateUserRequest {
  email?: string
  username?: string
  full_name?: string
  role?: 'admin' | 'curator' | 'researcher' | 'viewer'
  status?: 'active' | 'inactive' | 'suspended' | 'pending_verification'
}

export interface UserProfileResponse {
  user: UserPublic
}

export interface GenericSuccessResponse {
  message: string
}

export interface UserListParams {
  skip?: number
  limit?: number
  role?: string
  status_filter?: string
}

export async function fetchUsers(
  params: UserListParams = {},
  token?: string,
): Promise<UserListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchUsers')
  }

  const options: ApiRequestOptions<UserListResponse> = {
    token,
    params: {
      skip: params.skip ?? 0,
      limit: params.limit ?? 100,
      ...(params.role && { role: params.role }),
      ...(params.status_filter && { status_filter: params.status_filter }),
    },
  }

  return apiGet<UserListResponse>('/users', options)
}

export async function fetchUser(userId: string, token?: string): Promise<UserProfileResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchUser')
  }

  return apiGet<UserProfileResponse>(`/users/${userId}`, { token })
}

export async function createUser(
  payload: CreateUserRequest,
  token?: string,
): Promise<UserProfileResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createUser')
  }

  return apiPost<UserProfileResponse>('/users', payload, { token })
}

export async function updateUser(
  userId: string,
  payload: UpdateUserRequest,
  token?: string,
): Promise<UserProfileResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateUser')
  }

  return apiPut<UserProfileResponse>(`/users/${userId}`, payload, { token })
}

export async function deleteUser(
  userId: string,
  token?: string,
): Promise<GenericSuccessResponse> {
  if (!token) {
    throw new Error('Authentication token is required for deleteUser')
  }

  return apiDelete<GenericSuccessResponse>(`/users/${userId}`, { token })
}

export interface UserStatisticsResponse {
  total_users: number
  active_users: number
  inactive_users: number
  suspended_users: number
  pending_verification: number
  by_role: Record<string, number>
  recent_registrations: number
  recent_logins: number
}

const emptyUserStatistics = (): UserStatisticsResponse => ({
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  suspended_users: 0,
  pending_verification: 0,
  by_role: {},
  recent_registrations: 0,
  recent_logins: 0,
})

export async function fetchUserStatistics(
  token?: string,
): Promise<UserStatisticsResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchUserStatistics')
  }

  try {
    return await apiGet<UserStatisticsResponse>('/users/stats/overview', { token })
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const statusCode = error.response?.status
      if (statusCode === 500 || statusCode === 404) {
        return emptyUserStatistics()
      }
    }
    throw error
  }
}

export async function lockUser(
  userId: string,
  token?: string,
): Promise<GenericSuccessResponse> {
  if (!token) {
    throw new Error('Authentication token is required for lockUser')
  }

  return apiPost<GenericSuccessResponse>(`/users/${userId}/lock`, {}, { token })
}

export async function unlockUser(
  userId: string,
  token?: string,
): Promise<GenericSuccessResponse> {
  if (!token) {
    throw new Error('Authentication token is required for unlockUser')
  }

  return apiPost<GenericSuccessResponse>(`/users/${userId}/unlock`, {}, { token })
}

export async function activateUser(
  userId: string,
  token?: string,
): Promise<GenericSuccessResponse> {
  if (!token) {
    throw new Error('Authentication token is required for activateUser')
  }

  return apiPost<GenericSuccessResponse>(`/users/${userId}/activate`, {}, { token })
}
