// Authentication types for the Next.js frontend

export interface User {
  id: string
  email: string
  username: string
  full_name: string
  role: UserRole
  email_verified: boolean
  created_at?: string
  updated_at?: string
}

export enum UserRole {
  VIEWER = 'viewer',
  RESEARCHER = 'researcher',
  CURATOR = 'curator',
  ADMIN = 'admin'
}

export interface AuthSession {
  user: User & {
    access_token: string
    expires_at: number
  }
  expires: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  username: string
  full_name: string
  password: string
}

export interface LoginResponse {
  user: User
  access_token: string
  refresh_token: string
  expires_in: number
  token_type: string
}

export interface RegisterResponse {
  user: User
  message: string
}

export interface ForgotPasswordRequest {
  email: string
}

export interface ForgotPasswordResponse {
  message: string
}

export interface ResetPasswordRequest {
  token: string
  new_password: string
}

export interface ResetPasswordResponse {
  message: string
}

export interface RefreshTokenRequest {
  refresh_token: string
}

export interface RefreshTokenResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  token_type: string
}

// Permission types
export interface Permission {
  id: string
  name: string
  resource: string
  action: string
}

export interface RolePermissions {
  [role: string]: Permission[]
}
