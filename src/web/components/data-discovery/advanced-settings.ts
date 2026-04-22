"use client"

import type { ScheduleFrequency } from '@/types/data-source'

export interface SourceAdvancedSettings {
  scheduling: {
    enabled: boolean
    frequency: ScheduleFrequency
    timezone: string
    startTime: string | null
    cronExpression: string | null
  }
  notes: string
}

export const DEFAULT_ADVANCED_SETTINGS: SourceAdvancedSettings = {
  scheduling: {
    enabled: false,
    frequency: 'manual',
    timezone: 'UTC',
    startTime: null,
    cronExpression: null,
  },
  notes: '',
}

export function createDefaultAdvancedSettings(): SourceAdvancedSettings {
  return {
    scheduling: { ...DEFAULT_ADVANCED_SETTINGS.scheduling },
    notes: DEFAULT_ADVANCED_SETTINGS.notes,
  }
}
