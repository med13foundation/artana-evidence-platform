"use client"

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { inviteMemberAction } from '@/app/actions/research-spaces'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useInvitableUserSearch } from '@/hooks/use-invitable-user-search'
import {
  inviteMemberSchema,
  type InviteMemberFormData,
} from '@/lib/schemas/research-space'
import { MembershipRole } from '@/types/research-space'
import { InviteMemberUserPicker } from './InviteMemberUserPicker'
import { roleLabels } from './role-utils'

const DEFAULT_INVITE_MEMBER_VALUES: InviteMemberFormData = {
  user_id: '',
  role: MembershipRole.VIEWER,
}

interface InviteMemberDialogProps {
  afterInvite?: () => void
  open: boolean
  setDialogOpen: (open: boolean) => void
  spaceId: string
}

export function InviteMemberDialog({
  afterInvite,
  open,
  setDialogOpen,
  spaceId,
}: InviteMemberDialogProps) {
  const router = useRouter()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const userSearch = useInvitableUserSearch({ spaceId, open })

  const form = useForm<InviteMemberFormData>({
    resolver: zodResolver(inviteMemberSchema),
    defaultValues: DEFAULT_INVITE_MEMBER_VALUES,
  })

  useEffect(() => {
    if (!open) {
      form.reset(DEFAULT_INVITE_MEMBER_VALUES)
    }
  }, [form, open])

  const submitInvite = async (data: InviteMemberFormData) => {
    try {
      setIsSubmitting(true)
      const result = await inviteMemberAction(spaceId, {
        user_id: data.user_id,
        role: data.role as MembershipRole,
      })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      setDialogOpen(false)
      afterInvite?.()
      if (!afterInvite) {
        router.refresh()
      }
      toast.success('Invitation sent')
    } catch (error) {
      console.error('Failed to invite member:', error)
      toast.error('Failed to invite member')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite Member</DialogTitle>
          <DialogDescription>
            Invite a user to join this research space. They will receive a notification.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(submitInvite)} className="space-y-4">
            <FormField
              control={form.control}
              name="user_id"
              render={({ field }) => (
                <InviteMemberUserPicker
                  clearUserError={() => form.clearErrors('user_id')}
                  field={field}
                  searchState={userSearch}
                />
              )}
            />

            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <FormControl>
                    <Select
                      value={field.value}
                      onValueChange={(value) => field.onChange(value as MembershipRole)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select role" />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(MembershipRole).map((role) => (
                          <SelectItem key={role} value={role}>
                            {roleLabels[role]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormControl>
                  <FormDescription>
                    Select the role for the new member
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting || userSearch.selectedUser === null}
              >
                {isSubmitting ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : null}
                Send Invitation
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
