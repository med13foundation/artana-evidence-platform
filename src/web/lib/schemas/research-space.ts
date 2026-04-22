import { z } from 'zod'
import type {
  CreateSpaceRequest,
  InviteMemberRequest,
  MembershipRole,
  ResearchSpace,
  ResearchSpaceMembership,
  ResearchSpaceListResponse,
  MembershipListResponse,
  SpaceStatus,
  UpdateMemberRoleRequest,
  UpdateSpaceRequest,
} from '@/types/research-space'

// Zod schemas for validation
export const spaceStatusSchema = z.enum(['active', 'inactive', 'archived', 'suspended'])

export const membershipRoleSchema = z.enum(['owner', 'admin', 'curator', 'researcher', 'viewer'])

export const createSpaceSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100, 'Name cannot exceed 100 characters'),
  slug: z
    .string()
    .min(3, 'Slug must be at least 3 characters')
    .max(50, 'Slug cannot exceed 50 characters')
    .regex(/^[a-z0-9-]+$/, 'Slug must contain only lowercase letters, numbers, and hyphens'),
  description: z.string().max(500, 'Description cannot exceed 500 characters').optional(),
  governance_mode: z.enum(['FULL_AUTO', 'HUMAN_IN_LOOP']).default('FULL_AUTO'),
  relation_default_review_threshold: z
    .number()
    .min(0, 'Threshold must be >= 0')
    .max(1, 'Threshold must be <= 1')
    .default(0.7),
  relation_review_thresholds_text: z.string().default(''),
  settings: z.record(z.unknown()).optional(),
  tags: z.array(z.string()).max(10, 'Maximum 10 tags allowed').optional(),
})

export const updateSpaceSchema = z.object({
  name: z.string().min(1).max(100).optional(),
  description: z.string().max(500).optional(),
  settings: z.record(z.unknown()).optional(),
  tags: z.array(z.string()).max(10).optional(),
  status: spaceStatusSchema.optional(),
})

export const inviteMemberSchema = z.object({
  user_id: z.string().uuid('Invalid user ID'),
  role: membershipRoleSchema,
})

export const updateMemberRoleSchema = z.object({
  role: membershipRoleSchema,
})

// Type exports
export type CreateSpaceFormData = z.infer<typeof createSpaceSchema>
export type UpdateSpaceFormData = z.infer<typeof updateSpaceSchema>
export type InviteMemberFormData = z.infer<typeof inviteMemberSchema>
export type UpdateMemberRoleFormData = z.infer<typeof updateMemberRoleSchema>
