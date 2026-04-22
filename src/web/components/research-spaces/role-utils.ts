// Utility functions and constants for role management

import { MembershipRole } from '@/types/research-space'
import { cn } from '@/lib/utils'

export const roleLabels: Record<MembershipRole, string> = {
  [MembershipRole.OWNER]: 'Owner',
  [MembershipRole.ADMIN]: 'Admin',
  [MembershipRole.CURATOR]: 'Curator',
  [MembershipRole.RESEARCHER]: 'Researcher',
  [MembershipRole.VIEWER]: 'Viewer',
}

export const roleColors: Record<MembershipRole, string> = {
  [MembershipRole.OWNER]: 'bg-purple-500',
  [MembershipRole.ADMIN]: 'bg-blue-500',
  [MembershipRole.CURATOR]: 'bg-green-500',
  [MembershipRole.RESEARCHER]: 'bg-yellow-500',
  [MembershipRole.VIEWER]: 'bg-gray-500',
}

export const roleDescriptions: Record<MembershipRole, string> = {
  [MembershipRole.OWNER]: 'Full control over the space',
  [MembershipRole.ADMIN]: 'Can manage space settings and members',
  [MembershipRole.CURATOR]: 'Can create and manage data sources',
  [MembershipRole.RESEARCHER]: 'Can create data sources and view data',
  [MembershipRole.VIEWER]: 'Read-only access to space data',
}

export function canManageMembers(role: MembershipRole): boolean {
  return role === MembershipRole.OWNER || role === MembershipRole.ADMIN
}

export function canInviteMembers(role: MembershipRole): boolean {
  return role === MembershipRole.OWNER || role === MembershipRole.ADMIN
}

export function canModifySpace(role: MembershipRole): boolean {
  return role === MembershipRole.OWNER || role === MembershipRole.ADMIN
}

export function canManageMechanisms(role: MembershipRole): boolean {
  return (
    role === MembershipRole.OWNER ||
    role === MembershipRole.ADMIN ||
    role === MembershipRole.CURATOR
  )
}

export function canManageStatements(role: MembershipRole): boolean {
  return (
    role === MembershipRole.OWNER ||
    role === MembershipRole.ADMIN ||
    role === MembershipRole.CURATOR ||
    role === MembershipRole.RESEARCHER
  )
}
