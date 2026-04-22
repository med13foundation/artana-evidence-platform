"use client"

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'

import { createDictionaryVariableAction } from '@/app/actions/dictionary'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { JSONValue, JSONObject } from '@/types/generated'
import type {
  KernelDataType,
  KernelSensitivity,
  VariableDefinitionCreateRequest,
} from '@/types/dictionary'

type VariableFormState = {
  id: string
  canonical_name: string
  display_name: string
  data_type: KernelDataType
  domain_context: string
  sensitivity: KernelSensitivity
  preferred_unit: string
  description: string
  constraints_json: string
}

const DEFAULT_FORM: VariableFormState = {
  id: '',
  canonical_name: '',
  display_name: '',
  data_type: 'STRING',
  domain_context: 'general',
  sensitivity: 'INTERNAL',
  preferred_unit: '',
  description: '',
  constraints_json: '{}',
}

function isJsonValue(value: unknown): value is JSONValue {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return true
  }
  if (Array.isArray(value)) {
    return value.every((item) => isJsonValue(item))
  }
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).every((item) => isJsonValue(item))
  }
  return false
}

function isJsonObject(value: unknown): value is JSONObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  return Object.values(value as Record<string, unknown>).every((item) => isJsonValue(item))
}

export function CreateVariableCard() {
  const router = useRouter()
  const [form, setForm] = useState<VariableFormState>(DEFAULT_FORM)
  const [isCreating, setIsCreating] = useState(false)

  async function handleCreate() {
    const trimmedId = form.id.trim()
    const trimmedCanonical = form.canonical_name.trim()
    const trimmedDisplay = form.display_name.trim()

    if (!trimmedId || !trimmedCanonical || !trimmedDisplay) {
      toast.error('Please fill in: id, canonical_name, display_name')
      return
    }

    let parsedConstraints: JSONObject = {}
    if (form.constraints_json.trim().length > 0) {
      try {
        const parsed = JSON.parse(form.constraints_json) as unknown
        if (!isJsonObject(parsed)) {
          toast.error('Constraints must be a JSON object (values must be JSON primitives/arrays/objects).')
          return
        }
        parsedConstraints = parsed
      } catch {
        toast.error('Constraints must be valid JSON.')
        return
      }
    }

    const payload: VariableDefinitionCreateRequest = {
      id: trimmedId,
      canonical_name: trimmedCanonical,
      display_name: trimmedDisplay,
      data_type: form.data_type,
      domain_context: form.domain_context.trim() || 'general',
      sensitivity: form.sensitivity,
      preferred_unit: form.preferred_unit.trim() || null,
      constraints: parsedConstraints,
      description: form.description.trim() || null,
    }

    setIsCreating(true)
    const result = await createDictionaryVariableAction(payload)
    setIsCreating(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Variable created')
    setForm(DEFAULT_FORM)
    router.refresh()
  }

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">Create Variable</CardTitle>
        <CardDescription>
          Add a new variable definition to the dictionary. This is admin-only and globally shared.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="var-id">ID</Label>
          <Input
            id="var-id"
            placeholder="VAR_GENE_SYMBOL"
            value={form.id}
            onChange={(e) => setForm((prev) => ({ ...prev, id: e.target.value }))}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="var-canonical">Canonical Name</Label>
          <Input
            id="var-canonical"
            placeholder="gene_symbol"
            value={form.canonical_name}
            onChange={(e) => setForm((prev) => ({ ...prev, canonical_name: e.target.value }))}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="var-display">Display Name</Label>
          <Input
            id="var-display"
            placeholder="Gene Symbol"
            value={form.display_name}
            onChange={(e) => setForm((prev) => ({ ...prev, display_name: e.target.value }))}
          />
        </div>
        <div className="space-y-2">
          <Label>Data Type</Label>
          <Select
            value={form.data_type}
            onValueChange={(value) => setForm((prev) => ({ ...prev, data_type: value as KernelDataType }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select data type" />
            </SelectTrigger>
            <SelectContent>
              {(['INTEGER', 'FLOAT', 'STRING', 'DATE', 'CODED', 'BOOLEAN', 'JSON'] as const).map((dt) => (
                <SelectItem key={dt} value={dt}>
                  {dt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="var-domain">Domain Context</Label>
          <Input
            id="var-domain"
            placeholder="genomics"
            value={form.domain_context}
            onChange={(e) => setForm((prev) => ({ ...prev, domain_context: e.target.value }))}
          />
        </div>
        <div className="space-y-2">
          <Label>Sensitivity</Label>
          <Select
            value={form.sensitivity}
            onValueChange={(value) => setForm((prev) => ({ ...prev, sensitivity: value as KernelSensitivity }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select sensitivity" />
            </SelectTrigger>
            <SelectContent>
              {(['PUBLIC', 'INTERNAL', 'PHI'] as const).map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="var-unit">Preferred Unit</Label>
          <Input
            id="var-unit"
            placeholder="mmHg"
            value={form.preferred_unit}
            onChange={(e) => setForm((prev) => ({ ...prev, preferred_unit: e.target.value }))}
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="var-desc">Description</Label>
          <Textarea
            id="var-desc"
            placeholder="Optional description"
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="var-constraints">Constraints (JSON)</Label>
          <Textarea
            id="var-constraints"
            value={form.constraints_json}
            onChange={(e) => setForm((prev) => ({ ...prev, constraints_json: e.target.value }))}
          />
        </div>
        <div className="md:col-span-2">
          <Button onClick={() => handleCreate()} disabled={isCreating} className="w-full sm:w-auto">
            <Plus className="mr-2 size-4" />
            Create
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
