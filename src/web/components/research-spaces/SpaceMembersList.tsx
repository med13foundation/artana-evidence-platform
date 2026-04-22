"use client"
import { MembershipRole, type ResearchSpaceMembership } from '@/types/research-space'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { UserPlus } from 'lucide-react'
import { Loader2 } from 'lucide-react'
import { roleColors, roleLabels } from './role-utils'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface SpaceMembersListProps {
  memberships: ResearchSpaceMembership[]
  isLoading: boolean
  errorMessage: string | null
  onInvite?: () => void
  onUpdateRole?: (membershipId: string, nextRole: MembershipRole) => Promise<void> | void
  onRemove?: (membershipId: string) => void
  canManage?: boolean
  pendingMembershipId?: string | null
}

function getMembershipDisplayName(membership: ResearchSpaceMembership): string {
  const fullName = membership.user?.full_name?.trim()
  if (fullName) {
    return fullName
  }

  const username = membership.user?.username?.trim()
  if (username) {
    return username
  }

  return membership.user_id
}

export function SpaceMembersList({
  memberships,
  isLoading,
  errorMessage,
  onInvite,
  onUpdateRole,
  onRemove,
  canManage = false,
  pendingMembershipId = null,
}: SpaceMembersListProps) {
  const handleRemove = async (membershipId: string) => {
    if (!onRemove) {
      return
    }
    onRemove(membershipId)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
        <p className="text-sm text-destructive">
          Failed to load members: {errorMessage}
        </p>
      </div>
    )
  }

  const editableRoles = [
    MembershipRole.ADMIN,
    MembershipRole.CURATOR,
    MembershipRole.RESEARCHER,
    MembershipRole.VIEWER,
  ] as const

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-2xl font-bold tracking-tight">Members</h2>
          <p className="text-sm text-muted-foreground">
            {memberships.length} member{memberships.length !== 1 ? 's' : ''}
          </p>
        </div>
        {canManage && onInvite && (
          <Button onClick={onInvite}>
            <UserPlus className="mr-2 size-4" />
            Invite Member
          </Button>
        )}
      </div>

      {memberships.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="mb-4 text-muted-foreground">No members yet.</p>
          {canManage && onInvite && (
            <Button onClick={onInvite} variant="outline">
              <UserPlus className="mr-2 size-4" />
              Invite your first member
            </Button>
          )}
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Joined</TableHead>
                {canManage && <TableHead className="w-[100px]">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {memberships.map((membership) => {
                const displayName = getMembershipDisplayName(membership)

                return (
                  <TableRow key={membership.id}>
                    <TableCell className="font-medium">{displayName}</TableCell>
                    <TableCell>
                      {canManage && onUpdateRole && membership.role !== MembershipRole.OWNER ? (
                        <div className="flex items-center gap-2">
                          <Label className="sr-only" htmlFor={`space-role-${membership.id}`}>
                            Role for {displayName}
                          </Label>
                          <Select
                            value={membership.role}
                            onValueChange={(value: MembershipRole) => {
                              void onUpdateRole(membership.id, value)
                            }}
                            disabled={pendingMembershipId === membership.id}
                          >
                            <SelectTrigger
                              id={`space-role-${membership.id}`}
                              className="h-9 w-[160px]"
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {editableRoles.map((role) => (
                                <SelectItem key={role} value={role}>
                                  {roleLabels[role]}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {pendingMembershipId === membership.id ? (
                            <Loader2 className="size-4 animate-spin text-muted-foreground" />
                          ) : null}
                        </div>
                      ) : (
                        <Badge
                          className={cn(
                            roleColors[membership.role],
                            'text-white'
                          )}
                        >
                          {roleLabels[membership.role]}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {membership.is_active ? (
                        <Badge variant="outline" className="border-green-200 bg-green-50 text-green-700">
                          Active
                        </Badge>
                      ) : membership.joined_at ? (
                        <Badge variant="outline">Inactive</Badge>
                      ) : (
                        <Badge variant="outline" className="border-yellow-200 bg-yellow-50 text-yellow-700">
                          Pending
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {membership.joined_at
                        ? new Date(membership.joined_at).toLocaleDateString()
                        : membership.invited_at
                        ? `Invited ${new Date(membership.invited_at).toLocaleDateString()}`
                        : '-'}
                    </TableCell>
                    {canManage && (
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {membership.role !== MembershipRole.OWNER && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRemove(membership.id)}
                              disabled={pendingMembershipId === membership.id}
                            >
                              Remove
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
