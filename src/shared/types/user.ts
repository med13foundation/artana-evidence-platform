import { z } from 'zod'

// Enums
export enum UserRole {
  ADMIN = 'admin',
  RESEARCHER = 'researcher',
  CURATOR = 'curator',
  VIEWER = 'viewer',
}

export enum UserStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  PENDING = 'pending',
  SUSPENDED = 'suspended',
}

export enum Permission {
  // Data Source Permissions
  DATA_SOURCE_READ = 'data_source:read',
  DATA_SOURCE_CREATE = 'data_source:create',
  DATA_SOURCE_UPDATE = 'data_source:update',
  DATA_SOURCE_DELETE = 'data_source:delete',
  DATA_SOURCE_INGEST = 'data_source:ingest',

  // User Management Permissions
  USER_READ = 'user:read',
  USER_CREATE = 'user:create',
  USER_UPDATE = 'user:update',
  USER_DELETE = 'user:delete',
  USER_MANAGE_ROLES = 'user:manage_roles',

  // System Permissions
  SYSTEM_READ = 'system:read',
  SYSTEM_CONFIG = 'system:config',
  SYSTEM_BACKUP = 'system:backup',
  AUDIT_READ = 'audit:read',

  // Gene/Variant Permissions
  GENE_READ = 'gene:read',
  GENE_CREATE = 'gene:create',
  GENE_UPDATE = 'gene:update',
  VARIANT_READ = 'variant:read',
  VARIANT_CREATE = 'variant:create',
  VARIANT_UPDATE = 'variant:update',

  // Evidence Permissions
  EVIDENCE_READ = 'evidence:read',
  EVIDENCE_CREATE = 'evidence:create',
  EVIDENCE_UPDATE = 'evidence:update',
  EVIDENCE_REVIEW = 'evidence:review',
}

// Core Types
export interface User {
  id: string
  email: string
  username?: string
  firstName?: string
  lastName?: string
  role: UserRole
  status: UserStatus
  permissions: Permission[]
  profile?: UserProfile
  preferences?: UserPreferences
  lastLoginAt?: string
  createdAt: string
  updatedAt: string
}

export interface UserProfile {
  avatar?: string
  bio?: string
  organization?: string
  department?: string
  jobTitle?: string
  phone?: string
  timezone: string
  language: string
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system'
  notifications: NotificationPreferences
  dashboard: DashboardPreferences
}

export interface NotificationPreferences {
  email: boolean
  inApp: boolean
  ingestionComplete: boolean
  qualityIssues: boolean
  systemAlerts: boolean
  weeklyReports: boolean
}

export interface DashboardPreferences {
  defaultView: 'overview' | 'data-sources' | 'analytics'
  itemsPerPage: number
  autoRefresh: boolean
  refreshInterval: number
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  expiresIn: number
  tokenType: string
}

export interface LoginRequest {
  email: string
  password: string
  rememberMe?: boolean
}

export interface LoginResponse {
  user: User
  tokens: AuthTokens
}

export interface RegisterRequest {
  email: string
  password: string
  firstName?: string
  lastName?: string
  organization?: string
}

export interface PasswordResetRequest {
  email: string
}

export interface PasswordResetConfirmRequest {
  token: string
  newPassword: string
}

export interface UserUpdateRequest {
  firstName?: string
  lastName?: string
  profile?: Partial<UserProfile>
  preferences?: Partial<UserPreferences>
}

export interface RoleAssignment {
  userId: string
  role: UserRole
  permissions?: Permission[]
}

// API Response Types
export interface UserListResponse {
  users: User[]
  total: number
  page: number
  limit: number
}

export interface UserActivity {
  id: string
  userId: string
  action: string
  resource: string
  details?: Record<string, unknown>
  ipAddress?: string
  userAgent?: string
  requestId?: string
  success?: boolean
  timestamp: string
}

export interface AuditLog {
  id: string
  userId?: string
  action: string
  resource: string
  resourceId?: string
  oldValues?: Record<string, unknown>
  newValues?: Record<string, unknown>
  ipAddress?: string
  userAgent?: string
  requestId?: string
  success?: boolean
  timestamp: string
}

// Zod Schemas for Validation
export const UserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  username: z.string().optional(),
  firstName: z.string().optional(),
  lastName: z.string().optional(),
  role: z.nativeEnum(UserRole),
  status: z.nativeEnum(UserStatus),
  permissions: z.array(z.nativeEnum(Permission)),
  profile: z.object({
    avatar: z.string().url().optional(),
    bio: z.string().optional(),
    organization: z.string().optional(),
    department: z.string().optional(),
    jobTitle: z.string().optional(),
    phone: z.string().optional(),
    timezone: z.string(),
    language: z.string(),
  }).optional(),
  preferences: z.object({
    theme: z.enum(['light', 'dark', 'system']),
    notifications: z.object({
      email: z.boolean(),
      inApp: z.boolean(),
      ingestionComplete: z.boolean(),
      qualityIssues: z.boolean(),
      systemAlerts: z.boolean(),
      weeklyReports: z.boolean(),
    }),
    dashboard: z.object({
      defaultView: z.enum(['overview', 'data-sources', 'analytics']),
      itemsPerPage: z.number().int().positive(),
      autoRefresh: z.boolean(),
      refreshInterval: z.number().int().positive(),
    }),
  }).optional(),
  lastLoginAt: z.string().datetime().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})

export const LoginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  rememberMe: z.boolean().optional(),
})

export const RegisterRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  firstName: z.string().optional(),
  lastName: z.string().optional(),
  organization: z.string().optional(),
})
