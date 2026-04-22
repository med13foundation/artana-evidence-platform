"use client"

import { forwardRef, useEffect, useState } from 'react'
import type { ComponentPropsWithoutRef, ElementRef } from 'react'

import type { ModelSpec } from '@/types/ai-models'
import { fetchAvailableModelsClient } from '@/lib/client/ai-models'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'

interface AiModelSelectorProps {
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
}

/**
 * Model selector component for choosing AI models.
 * Fetches available models on mount and displays them with cost/capability badges.
 */
export const AiModelSelector = forwardRef<
  ElementRef<typeof SelectTrigger>,
  AiModelSelectorProps & Omit<ComponentPropsWithoutRef<typeof SelectTrigger>, 'value'>
>(function AiModelSelector(
  { value, onChange, disabled, ...triggerProps },
  ref,
) {
  const [availableModels, setAvailableModels] = useState<ModelSpec[]>([])
  const [defaultModelId, setDefaultModelId] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    setIsLoading(true)
    fetchAvailableModelsClient()
      .then((response) => {
        // Filter to only models that support query_generation
        const queryModels = response.models.filter((m) =>
          m.capabilities.includes('query_generation'),
        )
        setAvailableModels(queryModels)
        setDefaultModelId(response.default_query_model)
      })
      .catch((error) => {
        console.error('Failed to load available models', error)
        toast.error('Failed to load available models')
      })
      .finally(() => {
        setIsLoading(false)
      })
  }, [])

  const getCostTierBadgeVariant = (tier: string) => {
    switch (tier) {
      case 'low':
        return 'secondary'
      case 'medium':
        return 'default'
      case 'high':
        return 'destructive'
      default:
        return 'outline'
    }
  }

  return (
    <Select
      value={value ?? 'default'}
      onValueChange={(newValue) => onChange(newValue === 'default' ? null : newValue)}
      disabled={disabled || isLoading}
    >
      <SelectTrigger ref={ref} {...triggerProps}>
        <SelectValue placeholder={isLoading ? 'Loading models...' : 'Select a model'} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">
          <div className="flex items-center gap-2">
            <span>System default</span>
            {defaultModelId && (
              <span className="text-xs text-slate-500 dark:text-slate-400">
                ({availableModels.find((m) => m.model_id === defaultModelId)?.display_name ?? defaultModelId})
              </span>
            )}
          </div>
        </SelectItem>
        {availableModels.map((model) => (
          <SelectItem key={model.model_id} value={model.model_id}>
            <div className="flex items-center gap-2">
              <span>{model.display_name}</span>
              <Badge variant={getCostTierBadgeVariant(model.cost_tier)} className="text-xs">
                {model.cost_tier}
              </Badge>
              {model.is_reasoning_model && (
                <Badge variant="outline" className="text-xs">
                  reasoning
                </Badge>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
})
