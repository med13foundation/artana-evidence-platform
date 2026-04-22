"use client"

import { useEffect, useId, useState } from 'react'
import { useWatch, type Control, type UseFormSetValue } from 'react-hook-form'

import type { ScheduleFrequency } from '@/types/data-source'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import type { ScheduleFormValues } from './DataSourceScheduleDialog'

type ScheduleMode = 'daily' | 'interval'

const DAILY_INTERVAL_HOURS = 24
const ALL_WEEKDAYS = [1, 2, 3, 4, 5, 6, 0] as const
const WEEKDAY_OPTIONS = [
  { label: 'Mo', value: 1 },
  { label: 'Tu', value: 2 },
  { label: 'We', value: 3 },
  { label: 'Th', value: 4 },
  { label: 'Fr', value: 5 },
  { label: 'Sa', value: 6 },
  { label: 'Su', value: 0 },
] as const

function toTimeInput(value?: string): string {
  if (!value) {
    return '09:00'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return '09:00'
  }
  const hours = String(parsed.getHours()).padStart(2, '0')
  const minutes = String(parsed.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

function toDatetimeLocal(existingValue: string | undefined, timeValue: string): string {
  const baseline = existingValue ? new Date(existingValue) : new Date()
  const resolved = Number.isNaN(baseline.getTime()) ? new Date() : baseline
  const [hoursPart, minutesPart] = timeValue.split(':')
  const hours = Number.isNaN(Number(hoursPart)) ? 9 : Number(hoursPart)
  const minutes = Number.isNaN(Number(minutesPart)) ? 0 : Number(minutesPart)
  resolved.setHours(hours, minutes, 0, 0)
  const yyyy = String(resolved.getFullYear())
  const mm = String(resolved.getMonth() + 1).padStart(2, '0')
  const dd = String(resolved.getDate()).padStart(2, '0')
  const hh = String(resolved.getHours()).padStart(2, '0')
  const min = String(resolved.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${min}`
}

function sameWeekdays(left: number[], right: number[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((value, index) => value === right[index])
}

function parseWeekdayField(rawWeekdays: string): number[] {
  if (rawWeekdays === '*') {
    return [...ALL_WEEKDAYS]
  }
  const parsed = rawWeekdays
    .split(',')
    .map((part) => Number.parseInt(part.trim(), 10))
    .map((value) => (value === 7 ? 0 : value))
    .filter((value) => Number.isInteger(value) && value >= 0 && value <= 6)
  if (parsed.length === 0) {
    return [...ALL_WEEKDAYS]
  }
  const unique = new Set(parsed)
  return WEEKDAY_OPTIONS.filter((option) => unique.has(option.value)).map((option) => option.value)
}

function cronDayOfWeek(days: number[]): string {
  if (days.length === ALL_WEEKDAYS.length) {
    return '*'
  }
  return days.join(',')
}

function parseCronExpression(
  expression: string | undefined,
): { mode: ScheduleMode; intervalHours: number; weekdays: number[]; time: string } | null {
  if (!expression) {
    return null
  }
  const fields = expression.trim().split(/\s+/)
  if (fields.length !== 5) {
    return null
  }
  const [minuteField, hourField, _domField, _monthField, weekdayField] = fields
  const minute = Number.parseInt(minuteField, 10)
  if (Number.isNaN(minute) || minute < 0 || minute > 59) {
    return null
  }

  const weekdays = parseWeekdayField(weekdayField)
  const minuteText = String(minute).padStart(2, '0')

  if (hourField.startsWith('*/')) {
    const intervalValue = Number.parseInt(hourField.slice(2), 10)
    if (!Number.isNaN(intervalValue) && intervalValue > 0 && intervalValue <= 24) {
      return {
        mode: 'interval',
        intervalHours: intervalValue,
        weekdays,
        time: `00:${minuteText}`,
      }
    }
  }

  if (hourField === '*') {
    return {
      mode: 'interval',
      intervalHours: 1,
      weekdays,
      time: `00:${minuteText}`,
    }
  }

  const hour = Number.parseInt(hourField, 10)
  if (Number.isNaN(hour) || hour < 0 || hour > 23) {
    return null
  }

  return {
    mode: 'daily',
    intervalHours: DAILY_INTERVAL_HOURS,
    weekdays,
    time: `${String(hour).padStart(2, '0')}:${minuteText}`,
  }
}

function deriveUiState(
  frequency: ScheduleFrequency,
  cronExpression: string | undefined,
  startTime: string | undefined,
): { mode: ScheduleMode; intervalHours: number; weekdays: number[]; time: string } {
  if (frequency === 'cron') {
    const parsed = parseCronExpression(cronExpression)
    if (parsed) {
      return parsed
    }
  }
  if (frequency === 'hourly') {
    return {
      mode: 'interval',
      intervalHours: 1,
      weekdays: [...ALL_WEEKDAYS],
      time: toTimeInput(startTime),
    }
  }
  if (frequency === 'weekly') {
    const parsedStart = startTime ? new Date(startTime) : null
    const weekday = parsedStart && !Number.isNaN(parsedStart.getTime()) ? (parsedStart.getDay() + 6) % 7 + 1 : 1
    const normalizedWeekday = weekday === 7 ? 0 : weekday
    return {
      mode: 'daily',
      intervalHours: DAILY_INTERVAL_HOURS,
      weekdays: [normalizedWeekday],
      time: toTimeInput(startTime),
    }
  }
  return {
    mode: 'daily',
    intervalHours: DAILY_INTERVAL_HOURS,
    weekdays: [...ALL_WEEKDAYS],
    time: toTimeInput(startTime),
  }
}

interface DataSourceScheduleFieldsProps {
  control: Control<ScheduleFormValues>
  setValue: UseFormSetValue<ScheduleFormValues>
}

export function DataSourceScheduleFields({
  control,
  setValue,
}: DataSourceScheduleFieldsProps) {
  const scheduleTimeInputId = useId()
  const intervalHoursInputId = useId()
  const frequency = (useWatch({ control, name: 'frequency' }) ?? 'manual') as ScheduleFrequency
  const cronExpression = useWatch({ control, name: 'cronExpression' }) ?? ''
  const startTime = useWatch({ control, name: 'startTime' }) ?? ''

  const initialUi = deriveUiState(frequency, cronExpression || undefined, startTime || undefined)
  const [mode, setMode] = useState<ScheduleMode>(initialUi.mode)
  const [timeValue, setTimeValue] = useState(initialUi.time)
  const [intervalHours, setIntervalHours] = useState(initialUi.intervalHours)
  const [weekdays, setWeekdays] = useState<number[]>(initialUi.weekdays)
  const allDaysSelected = weekdays.length === ALL_WEEKDAYS.length

  useEffect(() => {
    const derived = deriveUiState(
      frequency,
      cronExpression ?? undefined,
      startTime ?? undefined,
    )
    setMode((current) => (current === derived.mode ? current : derived.mode))
    setTimeValue((current) => (current === derived.time ? current : derived.time))
    setIntervalHours((current) =>
      current === derived.intervalHours ? current : derived.intervalHours,
    )
    setWeekdays((current) =>
      sameWeekdays(current, derived.weekdays) ? current : derived.weekdays,
    )
  }, [frequency, cronExpression, startTime])

  useEffect(() => {
    const nextStartTime = toDatetimeLocal(startTime, timeValue)
    if (startTime !== nextStartTime) {
      setValue('startTime', nextStartTime, { shouldDirty: true })
    }

    const [hoursPart, minutesPart] = timeValue.split(':')
    const hour = Number.parseInt(hoursPart, 10)
    const minute = Number.parseInt(minutesPart, 10)
    const normalizedHour = Number.isNaN(hour) ? 9 : Math.min(Math.max(hour, 0), 23)
    const normalizedMinute = Number.isNaN(minute) ? 0 : Math.min(Math.max(minute, 0), 59)
    const dayOfWeek = cronDayOfWeek(weekdays)
    const safeInterval = Math.min(Math.max(intervalHours, 1), 24)
    let nextFrequency: ScheduleFrequency = 'daily'
    let nextCronExpression = ''

    if (mode === 'daily') {
      if (allDaysSelected) {
        nextFrequency = 'daily'
      } else {
        nextFrequency = 'cron'
        nextCronExpression = `${normalizedMinute} ${normalizedHour} * * ${dayOfWeek}`
      }
    } else if (safeInterval === DAILY_INTERVAL_HOURS) {
      if (allDaysSelected) {
        nextFrequency = 'daily'
      } else {
        nextFrequency = 'cron'
        nextCronExpression = `${normalizedMinute} ${normalizedHour} * * ${dayOfWeek}`
      }
    } else if (safeInterval === 1 && allDaysSelected) {
      nextFrequency = 'hourly'
    } else {
      nextFrequency = 'cron'
      nextCronExpression = `${normalizedMinute} */${safeInterval} * * ${dayOfWeek}`
    }

    if (frequency !== nextFrequency) {
      setValue('frequency', nextFrequency, { shouldDirty: true })
    }
    if (cronExpression !== nextCronExpression) {
      setValue('cronExpression', nextCronExpression, { shouldDirty: true })
    }
  }, [
    allDaysSelected,
    cronExpression,
    frequency,
    intervalHours,
    mode,
    setValue,
    startTime,
    timeValue,
    weekdays,
  ])

  const toggleWeekday = (day: number) => {
    setWeekdays((current) => {
      if (current.includes(day)) {
        if (current.length === 1) {
          return current
        }
        return current.filter((value) => value !== day)
      }
      const next = [...current, day]
      return WEEKDAY_OPTIONS.filter((option) => next.includes(option.value)).map((option) => option.value)
    })
  }

  return (
    <>
      <div className="space-y-3 rounded-lg border p-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">Schedule</div>
          <div className="inline-flex rounded-full border bg-muted/50 p-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn(
                'h-8 rounded-full px-4',
                mode === 'daily' ? 'bg-background shadow-sm' : 'text-muted-foreground',
              )}
              onClick={() => setMode('daily')}
            >
              Daily
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn(
                'h-8 rounded-full px-4',
                mode === 'interval' ? 'bg-background shadow-sm' : 'text-muted-foreground',
              )}
              onClick={() => setMode('interval')}
            >
              Interval
            </Button>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-[minmax(180px,220px)_1fr] md:items-center">
          <div className="flex items-center gap-2">
            <Input
              id={scheduleTimeInputId}
              name="schedule_time"
              type="time"
              aria-label="Schedule time"
              value={timeValue}
              onChange={(event) => setTimeValue(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_OPTIONS.map((weekday) => {
              const active = weekdays.includes(weekday.value)
              return (
                <Button
                  key={weekday.label}
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleWeekday(weekday.value)}
                  className={cn(
                    'h-9 min-w-9 rounded-full border px-3 text-xs',
                    active
                      ? 'border-foreground bg-foreground text-background'
                      : 'border-muted-foreground/40 text-muted-foreground',
                  )}
                >
                  {weekday.label}
                </Button>
              )
            })}
          </div>
        </div>

        {mode === 'interval' && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Run every</span>
            <Input
              id={intervalHoursInputId}
              name="interval_hours"
              type="number"
              min={1}
              max={24}
              aria-label="Interval hours"
              value={intervalHours}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10)
                if (Number.isNaN(parsed)) {
                  setIntervalHours(1)
                  return
                }
                setIntervalHours(Math.min(Math.max(parsed, 1), 24))
              }}
              className="h-9 w-24"
            />
            <span>hours</span>
          </div>
        )}

        <FormDescription>
          This schedule will be required before the source can be activated.
        </FormDescription>
        <FormField
          control={control}
          name="frequency"
          render={() => (
            <FormItem>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <FormField
        control={control}
        name="timezone"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Timezone</FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormDescription>
              Specify the timezone for scheduler calculations.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  )
}
