import type { UseFormReturn } from 'react-hook-form'

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

import type { AiConfigFormValues } from './DataSourceAiConfigDialog'
import { AiModelSelector } from './AiModelSelector'

interface AiManagedConfigFieldsProps {
  form: UseFormReturn<AiConfigFormValues>
  isPubMedSource: boolean
}

interface PubMedConfigFieldsProps {
  form: UseFormReturn<AiConfigFormValues>
}

export function AiManagedConfigFields({ form, isPubMedSource }: AiManagedConfigFieldsProps) {
  return (
    <>
      <FormField
        control={form.control}
        name="model_id"
        render={({ field }) => (
          <FormItem>
            <FormLabel>AI Model</FormLabel>
            <FormControl>
              <AiModelSelector
                value={field.value}
                onChange={field.onChange}
                name={field.name}
                aria-label="AI model"
              />
            </FormControl>
            <FormDescription>
              Choose which AI model powers query generation for this source.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="use_research_space_context"
        render={({ field }) => (
          <FormItem className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <FormLabel>Use research space context</FormLabel>
              <FormDescription>
                Provide the research space description to the agent.
              </FormDescription>
            </div>
            <FormControl>
              <Switch
                checked={field.value}
                onCheckedChange={field.onChange}
                name={field.name}
                aria-label="Use research space context"
              />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="agent_prompt"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {isPubMedSource ? 'Query description (optional)' : 'Agent instructions (optional)'}
            </FormLabel>
            <FormControl>
              <Textarea
                placeholder={
                  isPubMedSource
                    ? 'e.g. Focus on MED13 mechanisms in plants, prioritize open-access full-text papers.'
                    : 'e.g. Focus on clinical case studies and mechanistic pathways.'
                }
                className="min-h-[100px]"
                {...field}
              />
            </FormControl>
            <FormDescription>
              {isPubMedSource
                ? 'Describe the research intent in plain text. The AI will build/refine the executable query.'
                : 'Custom instructions to steer the agent behavior.'}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  )
}

export function PubMedConfigFields({ form }: PubMedConfigFieldsProps) {
  return (
    <>
      <div className="rounded-md border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
        Warning: changing PubMed query configuration resets the incremental checkpoint. The next runs may
        revisit older papers before progressing to newer ones.
      </div>
      <FormField
        control={form.control}
        name="max_results"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Per-run paper cap (`max_results`)</FormLabel>
            <FormControl>
              <Input
                type="number"
                min={1}
                max={10000}
                name={field.name}
                onBlur={field.onBlur}
                ref={field.ref}
                value={field.value}
                onChange={(event) =>
                  field.onChange(
                    Number.isFinite(Number(event.target.value))
                      ? Number(event.target.value)
                      : 1,
                  )
                }
              />
            </FormControl>
            <FormDescription>
              Safety cap to avoid overload during each PubMed run.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="flex items-center justify-between rounded-md border p-3">
        <div className="space-y-0.5">
          <div className="text-sm font-medium">Open access only</div>
          <p className="text-sm text-muted-foreground">
            Locked on for PubMed sources so full text can be fetched legally.
          </p>
        </div>
        <div className="text-xs font-medium text-muted-foreground">ENFORCED</div>
      </div>
    </>
  )
}
