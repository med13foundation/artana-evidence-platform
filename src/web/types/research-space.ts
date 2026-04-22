// Research Spaces types for the Next.js frontend

export enum SpaceStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ARCHIVED = 'archived',
  SUSPENDED = 'suspended',
}

export enum MembershipRole {
  OWNER = 'owner',
  ADMIN = 'admin',
  CURATOR = 'curator',
  RESEARCHER = 'researcher',
  VIEWER = 'viewer',
}

export interface ResearchSpaceSettings {
  auto_approve?: boolean
  require_review?: boolean
  review_threshold?: number
  relation_governance_mode?: 'FULL_AUTO' | 'HUMAN_IN_LOOP'
  relation_auto_promotion?: {
    enabled?: boolean
    min_distinct_sources?: number
    min_aggregate_confidence?: number
    require_distinct_documents?: boolean
    require_distinct_runs?: boolean
    block_if_conflicting_evidence?: boolean
    min_evidence_tier?: string
    computational_min_distinct_sources?: number
    computational_min_aggregate_confidence?: number
    conflicting_confidence_threshold?: number
  }
  claim_non_persistable_baseline_ratio?: number
  claim_non_persistable_alert_ratio?: number
  relation_default_review_threshold?: number
  relation_review_thresholds?: Record<string, number>
  dictionary_agent_creation_policy?: 'ACTIVE' | 'PENDING_REVIEW'
  concept_agent_creation_policy?: 'ACTIVE' | 'PENDING_REVIEW'
  concept_policy_mode?: 'PRECISION' | 'BALANCED' | 'DISCOVERY'
  max_data_sources?: number
  allowed_source_types?: string[]
  sources?: {
    pubmed?: boolean
    marrvel?: boolean
    pdf?: boolean
    text?: boolean
  }
  public_read?: boolean
  allow_invites?: boolean
  email_notifications?: boolean
  notification_frequency?: string
  custom?: Record<string, string | number | boolean | null>
}

export interface ResearchSpace {
  id: string
  slug: string
  name: string
  description: string
  owner_id: string
  status: SpaceStatus
  settings: ResearchSpaceSettings
  tags: string[]
  created_at: string
  updated_at: string
}

export interface ResearchSpaceMembership {
  id: string
  space_id: string
  user_id: string
  role: MembershipRole
  invited_by: string | null
  invited_at: string | null
  joined_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  user?: ResearchSpaceMembershipUser | null
}

// Request types
export interface CreateSpaceRequest {
  name: string
  slug: string
  description?: string
  settings?: ResearchSpaceSettings
  tags?: string[]
}

export interface UpdateSpaceRequest {
  slug?: string
  name?: string
  description?: string
  settings?: ResearchSpaceSettings
  tags?: string[]
  status?: SpaceStatus
}

export interface InviteMemberRequest {
  user_id: string
  role: MembershipRole
}

export interface UpdateMemberRoleRequest {
  role: MembershipRole
}

// Response types
export interface ResearchSpaceListResponse {
  spaces: ResearchSpace[]
  total: number
  skip: number
  limit: number
}

export interface MembershipListResponse {
  memberships: ResearchSpaceMembership[]
  total: number
  skip: number
  limit: number
}

export interface ResearchSpaceMembershipUser {
  id: string
  email: string
  username: string
  full_name: string
}

export type MembershipWithUser = ResearchSpaceMembership
export type InvitableUserOption = ResearchSpaceMembershipUser

export interface InvitableUserSearchResponse {
  query: string
  users: InvitableUserOption[]
  total: number
  limit: number
}
