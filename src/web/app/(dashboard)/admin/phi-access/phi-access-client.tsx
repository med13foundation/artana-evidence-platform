"use client"

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCcw, ShieldCheck, ShieldX } from 'lucide-react'
import { toast } from 'sonner'

import { updateUserAction } from '@/app/actions/users'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { UserListResponse, UserPublic } from '@/lib/api/users'
import { replaceUserInLists, updateUserStatsCache } from '@/lib/query/admin-cache'
import { queryKeys } from '@/lib/query/query-keys'
import { usersQueryOptions } from '@/lib/query/query-options'

interface PhiAccessClientProps {
  users: UserListResponse | null
  usersError?: string | null
  currentUserId: string
}

function userHasPhiAccess(user: UserPublic): boolean {
  return user.role === 'admin'
}

export default function PhiAccessClient({
  users,
  usersError,
  currentUserId,
}: PhiAccessClientProps) {
  const queryClient = useQueryClient()
  const usersQuery = useQuery(
    usersQueryOptions({ skip: 0, limit: 500 }, users ?? undefined),
  )
  const rows = usersQuery.data?.users ?? users?.users ?? []
  const [roleDrafts, setRoleDrafts] = useState<Record<string, UserPublic['role']>>({})
  const [pendingUserId, setPendingUserId] = useState<string | null>(null)

  const phiUsers = rows.filter((row) => userHasPhiAccess(row))

  const onRoleChange = (userId: string, role: UserPublic['role']) => {
    setRoleDrafts((prev) => ({ ...prev, [userId]: role }))
  }

  const saveRole = async (user: UserPublic) => {
    const nextRole = roleDrafts[user.id]
    if (!nextRole || nextRole === user.role) {
      return
    }

    setPendingUserId(user.id)
    try {
      const result = await updateUserAction(user.id, { role: nextRole })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      replaceUserInLists(queryClient, result.data.user)
      updateUserStatsCache(queryClient, user, result.data.user)
      setRoleDrafts((prev) => {
        const next = { ...prev }
        delete next[user.id]
        return next
      })
      toast.success(`Updated role for ${user.full_name}`)
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.usersRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.userStats() }),
      ])
    } catch (error) {
      console.error('[PhiAccessClient] Failed to update role', error)
      toast.error('Unable to update user role')
    } finally {
      setPendingUserId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">PHI Access Management</h1>
          <p className="text-sm text-muted-foreground">
            PHI access is enforced via role-based policy. Admins can access PHI-scoped identifiers.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            void queryClient.invalidateQueries({ queryKey: queryKeys.usersRoot() })
          }}
          disabled={usersQuery.isFetching}
        >
          <RefreshCcw className="mr-2 size-4" />
          {usersQuery.isFetching ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Users with PHI Access</CardTitle>
            <CardDescription>
              Principals currently allowed to read PHI data under RLS policy.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {phiUsers.length}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Users without PHI Access</CardTitle>
            <CardDescription>
              Roles scoped to non-PHI workflows.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {Math.max(rows.length - phiUsers.length, 0)}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Role-to-PHI Mapping</CardTitle>
          <CardDescription>
            Current policy: `admin` grants PHI access. Other roles remain non-PHI.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usersError || usersQuery.isError ? (
            <div className="text-sm text-destructive">{usersError}</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">No users found.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Current Role</TableHead>
                  <TableHead>PHI Access</TableHead>
                  <TableHead>Role Update</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((user) => {
                  const effectiveRole = roleDrafts[user.id] ?? user.role
                  const isSaving = pendingUserId === user.id
                  const isSelf = user.id === currentUserId
                  const hasChanged = effectiveRole !== user.role

                  return (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="font-medium">{user.full_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{user.id}</div>
                      </TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{user.role}</Badge>
                      </TableCell>
                      <TableCell>
                        {userHasPhiAccess(user) ? (
                          <Badge>
                            <ShieldCheck className="mr-1 size-3" />
                            Allowed
                          </Badge>
                        ) : (
                          <Badge variant="secondary">
                            <ShieldX className="mr-1 size-3" />
                            Blocked
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="space-y-1">
                            <Label className="sr-only" htmlFor={`role-${user.id}`}>
                              Role
                            </Label>
                            <Select
                              value={effectiveRole}
                              onValueChange={(value: UserPublic['role']) =>
                                onRoleChange(user.id, value)
                              }
                              disabled={isSaving || isSelf}
                            >
                              <SelectTrigger id={`role-${user.id}`} className="w-[150px]">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="admin">admin</SelectItem>
                                <SelectItem value="curator">curator</SelectItem>
                                <SelectItem value="researcher">researcher</SelectItem>
                                <SelectItem value="viewer">viewer</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!hasChanged || isSaving || isSelf}
                            onClick={() => void saveRole(user)}
                          >
                            {isSaving ? (
                              <>
                                <Loader2 className="mr-2 size-4 animate-spin" />
                                Saving
                              </>
                            ) : (
                              'Save'
                            )}
                          </Button>
                        </div>
                        {isSelf ? (
                          <div className="mt-1 text-xs text-muted-foreground">
                            You cannot change your own role here.
                          </div>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
