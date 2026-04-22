"use client"

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { TemplateCreatePayload, TemplateCategory, TemplateResponse, TemplateUpdatePayload } from '@/types/template'
import { SourceType } from '@/types/data-source'
import { Textarea } from '@/components/ui/textarea'
import { Loader2 } from 'lucide-react'

const templateCategories = ['clinical', 'research', 'literature', 'genomic', 'phenotypic', 'ontology', 'other'] as const satisfies TemplateCategory[]
const templateSourceTypes = [
  'api',
  'file_upload',
  'database',
  'web_scraping',
  'pubmed',
  'clinvar',
] as const satisfies SourceType[]

const schema = z.object({
  name: z.string().min(1, 'Name is required').max(200),
  description: z.string().max(1000).optional(),
  category: z.enum(templateCategories),
  source_type: z.enum(templateSourceTypes),
  is_public: z.boolean().default(false),
  schema_definition: z.string().default('{"type":"object"}'),
  tags: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

interface TemplateDialogProps {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  template?: TemplateResponse
  onCreate?: (payload: TemplateCreatePayload) => Promise<unknown> | undefined
  onUpdate?: (payload: TemplateUpdatePayload['data']) => Promise<unknown> | undefined
}

export function TemplateDialog({
  mode,
  open,
  onOpenChange,
  template,
  onCreate,
  onUpdate,
}: TemplateDialogProps) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: template?.name ?? '',
      description: template?.description ?? '',
      category: template?.category ?? 'research',
      source_type: (template?.source_type as SourceType | undefined) ?? 'api',
      is_public: template?.is_public ?? false,
      schema_definition: template
        ? JSON.stringify(template.schema_definition, null, 2)
        : '{\n  "type": "object",\n  "properties": {}\n}',
      tags: template?.tags.join(', ') ?? '',
    },
  })

  useEffect(() => {
    if (template) {
      form.reset({
        name: template.name,
        description: template.description ?? '',
        category: template.category,
        source_type: template.source_type as SourceType,
        is_public: template.is_public,
        schema_definition: JSON.stringify(template.schema_definition, null, 2),
        tags: template.tags.join(', '),
      })
    } else if (mode === 'create') {
      form.reset({
        name: '',
        description: '',
        category: 'research',
        source_type: 'api',
        is_public: false,
        schema_definition: '{\n  "type": "object",\n  "properties": {}\n}',
        tags: '',
      })
    }
  }, [template, form, mode])

  const handleSubmit = async (values: FormValues) => {
    setSubmitError(null)
    try {
      const parsedSchema = JSON.parse(values.schema_definition || '{}')
      const tagsArray = values.tags
        ? values.tags.split(',').map((tag) => tag.trim()).filter(Boolean)
        : []

      if (mode === 'create') {
        await onCreate?.({
          name: values.name,
          description: values.description,
          category: values.category,
          source_type: values.source_type,
          schema_definition: parsedSchema,
          validation_rules: [],
          ui_config: {},
          tags: tagsArray,
          is_public: values.is_public,
        })
        form.reset()
      } else if (mode === 'edit') {
        await onUpdate?.({
          name: values.name,
          description: values.description,
          category: values.category,
          schema_definition: parsedSchema,
          validation_rules: template?.validation_rules ?? [],
          ui_config: template?.ui_config ?? {},
          tags: tagsArray,
        })
      }
      onOpenChange(false)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to create template')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? 'Create Template' : 'Edit Template'}</DialogTitle>
          <DialogDescription>
            {mode === 'create'
              ? 'Define a reusable data source template.'
              : 'Update template metadata and schema.'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="Phenotype API template" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="Short description (optional)" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Category</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select category" />
                        </SelectTrigger>
                        <SelectContent>
                          {templateCategories.map((cat) => (
                            <SelectItem key={cat} value={cat}>
                              {cat.replace('_', ' ')}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="source_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Source Type</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select source type" />
                        </SelectTrigger>
                        <SelectContent>
                          {templateSourceTypes.map((type) => (
                            <SelectItem key={type} value={type}>
                              {type.replace('_', ' ')}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="schema_definition"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Schema Definition (JSON)</FormLabel>
                  <FormControl>
                    <Textarea rows={5} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="tags"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tags</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="Comma-separated tags" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="is_public"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                  <FormLabel className="!mt-0">Public template</FormLabel>
                </FormItem>
              )}
            />
            {submitError && <p className="text-sm text-destructive">{submitError}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting && <Loader2 className="mr-2 size-4 animate-spin" />}
                {mode === 'create' ? 'Create Template' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
