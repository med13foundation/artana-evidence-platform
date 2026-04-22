"use client"

import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Trash2, Plus, Loader2 } from 'lucide-react'
import type { TemplateValidationRule } from '@/types/template'

const RULE_TYPES = ['required', 'pattern', 'range', 'enum', 'type', 'cross_reference', 'custom', 'format'] as const
const generateId = () =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)

interface ValidationRulesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  rules: TemplateValidationRule[]
  onSave: (rules: TemplateValidationRule[]) => Promise<void> | void
  isSaving?: boolean
}

interface RuleDraft {
  id: string
  field: string
  rule_type: string
  error_message: string
  parametersJson: string
}

export function ValidationRulesDialog({ open, onOpenChange, rules, onSave, isSaving }: ValidationRulesDialogProps) {
  const [drafts, setDrafts] = useState<RuleDraft[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setDrafts(
        rules.map((rule, index) => ({
          id: `${rule.field}-${index}`,
          field: rule.field,
          rule_type: rule.rule_type,
          error_message: rule.error_message,
          parametersJson: JSON.stringify(rule.parameters ?? {}, null, 2),
        })),
      )
      setError(null)
    }
  }, [open, rules])

  const updateDraft = (id: string, patch: Partial<RuleDraft>) => {
    setDrafts((current) => current.map((draft) => (draft.id === id ? { ...draft, ...patch } : draft)))
  }

  const addDraft = () => {
    setDrafts((current) => [
      ...current,
      {
        id: generateId(),
        field: '',
        rule_type: 'required',
        error_message: '',
        parametersJson: '{\n  \n}',
      },
    ])
  }

  const removeDraft = (id: string) => {
    setDrafts((current) => current.filter((draft) => draft.id !== id))
  }

  const handleSave = async () => {
    try {
      const normalized = drafts.map<TemplateValidationRule>((draft) => {
        const parsed = draft.parametersJson.trim() ? JSON.parse(draft.parametersJson) : {}
        if (typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error(`Parameters for "${draft.field || 'rule'}" must be a JSON object`)
        }
        return {
          field: draft.field.trim(),
          rule_type: draft.rule_type,
          error_message: draft.error_message.trim(),
          parameters: parsed as Record<string, unknown>,
        }
      })

      if (normalized.some((rule) => !rule.field)) {
        setError('Each rule requires a field name.')
        return
      }
      if (normalized.some((rule) => !rule.error_message)) {
        setError('Each rule requires an error message.')
        return
      }

      await onSave(normalized)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to parse validation rules')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit Validation Rules</DialogTitle>
          <DialogDescription>Manage template-level validation logic enforced before ingestion.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto pr-2">
          <div className="space-y-4">
            {drafts.length === 0 ? (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                No validation rules defined yet.
              </div>
            ) : (
              drafts.map((draft) => (
                <div key={draft.id} className="space-y-3 rounded-lg border p-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline">{draft.rule_type}</Badge>
                    <Button variant="ghost" size="sm" onClick={() => removeDraft(draft.id)}>
                      <Trash2 className="mr-2 size-4" />
                      Remove
                    </Button>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1">
                      <label className="text-sm font-medium">Field</label>
                      <Input value={draft.field} onChange={(event) => updateDraft(draft.id, { field: event.target.value })} />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium">Rule Type</label>
                      <select
                        className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm"
                        value={draft.rule_type}
                        onChange={(event) => updateDraft(draft.id, { rule_type: event.target.value })}
                      >
                        {RULE_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {type.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">Error Message</label>
                    <Input
                      value={draft.error_message}
                      onChange={(event) => updateDraft(draft.id, { error_message: event.target.value })}
                      placeholder="Describe the validation failure"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">Parameters (JSON)</label>
                    <Textarea
                      rows={4}
                      value={draft.parametersJson}
                      onChange={(event) => updateDraft(draft.id, { parametersJson: event.target.value })}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex items-center justify-between">
          <Button type="button" variant="outline" onClick={addDraft}>
            <Plus className="mr-2 size-4" />
            Add Rule
          </Button>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={handleSave} disabled={isSaving || drafts.length === 0}>
              {isSaving && <Loader2 className="mr-2 size-4 animate-spin" />}
              Save Rules
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
