"use client"

import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { Loader2 } from 'lucide-react'

import { configureDataSourceScheduleAction } from '@/app/actions/data-sources'
import type { DataSource } from '@/types/data-source'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Form } from '@/components/ui/form'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'

import { DataSourceScheduleFields } from './DataSourceScheduleFields'

const scheduleSchema = z.object({
  enabled: z.boolean().default(false),
  frequency: z.enum(['manual', 'hourly', 'daily', 'weekly', 'monthly', 'cron']),
  startTime: z.string().optional(),
  timezone: z.string().min(1, 'Timezone is required'),
  cronExpression: z.string().optional(),
})

export type ScheduleFormValues = z.infer<typeof scheduleSchema>

interface DataSourceScheduleDialogProps {
  source: DataSource | null
  spaceId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function toLocalDatetimeInput(value?: string | null): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export function DataSourceScheduleDialog({
  source,
  spaceId,
  open,
  onOpenChange,
}: DataSourceScheduleDialogProps) {
  const router = useRouter()
  const [isSavingSchedule, setIsSavingSchedule] = useState(false)
  const schedule = source?.ingestion_schedule

  const defaultValues = useMemo<ScheduleFormValues>(
    () => ({
      enabled: true,
      frequency: schedule?.frequency ?? 'manual',
      startTime: toLocalDatetimeInput(schedule?.start_time),
      timezone: schedule?.timezone ?? 'UTC',
      cronExpression: schedule?.cron_expression ?? '',
    }),
    [schedule],
  )

  const form = useForm<ScheduleFormValues>({
    resolver: zodResolver(scheduleSchema),
    defaultValues,
  })

  useEffect(() => {
    form.reset(defaultValues)
  }, [defaultValues, form, open])

  if (!source) {
    return null
  }

  const onSubmit = async (values: ScheduleFormValues) => {
    const normalizedFrequency = values.frequency === 'manual' ? 'daily' : values.frequency
    const payload = {
      enabled: true,
      frequency: normalizedFrequency,
      timezone: values.timezone,
      start_time: values.startTime ? new Date(values.startTime).toISOString() : null,
      cron_expression:
        normalizedFrequency === 'cron' ? values.cronExpression?.trim() || null : null,
    }

    try {
      setIsSavingSchedule(true)
      const result = await configureDataSourceScheduleAction(source.id, payload, spaceId)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success('Schedule updated')
      onOpenChange(false)
      router.refresh()
    } catch (error) {
      console.error('Failed to update schedule', error)
      toast.error('Failed to update schedule')
    } finally {
      setIsSavingSchedule(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[760px]">
        <DialogHeader>
          <DialogTitle>Configure ingestion schedule</DialogTitle>
          <DialogDescription>
            Control how often MED13 automatically ingests data from this source. A configured
            schedule is required before activating the source.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <DataSourceScheduleFields control={form.control} setValue={form.setValue} />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSavingSchedule}>
                {isSavingSchedule && (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                )}
                Save schedule
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
