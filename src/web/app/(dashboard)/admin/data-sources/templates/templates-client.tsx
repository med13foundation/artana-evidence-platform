"use client"

import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { createTemplateAction, deleteTemplateAction, updateTemplateAction } from '@/app/actions/templates'
import type { TemplateResponse, TemplateScope } from '@/types/template'
import { Badge } from '@/components/ui/badge'
import { Loader2, Plus, Trash2, Pencil, ExternalLink } from 'lucide-react'
import { TemplateDialog } from '@/components/templates/TemplateDialog'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'

interface TemplatesClientProps {
  templatesByScope: Record<TemplateScope, TemplateResponse[]>
  errorsByScope: Record<TemplateScope, string | null>
}

export default function TemplatesClient({ templatesByScope, errorsByScope }: TemplatesClientProps) {
  const router = useRouter()
  const [scope, setScope] = useState<TemplateScope>('available')
  const [dialogMode, setDialogMode] = useState<'create' | 'edit'>('create')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [activeTemplate, setActiveTemplate] = useState<TemplateResponse | undefined>(undefined)
  const [deleteTarget, setDeleteTarget] = useState<TemplateResponse | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const templates = templatesByScope[scope] ?? []
  const scopeError = errorsByScope[scope]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">Template Catalog</h1>
          <p className="text-sm text-muted-foreground">
            Manage reusable configurations for common data sources.
          </p>
        </div>
        <Button
          onClick={() => {
            setDialogMode('create')
            setActiveTemplate(undefined)
            setDialogOpen(true)
          }}
          className="w-full sm:w-auto"
        >
          <Plus className="mr-2 size-4" />
          Create Template
        </Button>
      </div>

      <Tabs value={scope} onValueChange={(value) => setScope(value as TemplateScope)}>
        <TabsList>
          <TabsTrigger value="available">Available</TabsTrigger>
          <TabsTrigger value="public">Public</TabsTrigger>
          <TabsTrigger value="mine">My Templates</TabsTrigger>
        </TabsList>
        <TabsContent value={scope} className="mt-4">
          {scopeError ? (
            <Card>
              <CardContent className="py-12 text-center text-destructive">
                {scopeError}
              </CardContent>
            </Card>
          ) : templates.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                No templates found for this scope.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {templates.map((template) => (
                <TemplateCard
                  key={template.id}
                  template={template}
                  onEdit={() => {
                    setActiveTemplate(template)
                    setDialogMode('edit')
                    setDialogOpen(true)
                  }}
                  onDelete={() => setDeleteTarget(template)}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <TemplateDialog
        mode={dialogMode}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        template={activeTemplate}
        onCreate={async (payload) => {
          const result = await createTemplateAction(payload)
          if (!result.success) {
            throw new Error(result.error)
          }
          toast.success('Template created')
          router.refresh()
        }}
        onUpdate={async (data) => {
          if (!activeTemplate) {
            return
          }
          const result = await updateTemplateAction({
            templateId: activeTemplate.id,
            data,
          })
          if (!result.success) {
            throw new Error(result.error)
          }
          toast.success('Template updated')
          router.refresh()
        }}
      />

      <ConfirmDeleteDialog
        template={deleteTarget}
        onCancel={() => {
          setDeleteLoading(false)
          setDeleteTarget(null)
        }}
        onConfirm={async () => {
          if (deleteTarget) {
            setDeleteLoading(true)
            const result = await deleteTemplateAction(deleteTarget.id)
            if (!result.success) {
              toast.error(result.error)
            } else {
              toast.success('Template deleted')
              router.refresh()
            }
            setDeleteLoading(false)
            setDeleteTarget(null)
          }
        }}
        isPending={deleteLoading}
      />
    </div>
  )
}

interface TemplateCardProps {
  template: TemplateResponse
  onEdit?: () => void
  onDelete?: () => void
}

function TemplateCard({ template, onEdit, onDelete }: TemplateCardProps) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-lg">{template.name}</CardTitle>
            <CardDescription>{template.description || 'No description'}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {template.is_public && <Badge variant="outline">Public</Badge>}
            <Button variant="ghost" size="icon" asChild>
              <Link href={`/admin/data-sources/templates/${template.id}`}>
                <ExternalLink className="size-4" />
                <span className="sr-only">View details</span>
              </Link>
            </Button>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil className="mr-2 size-4" />
            Edit
          </Button>
          <Button variant="ghost" size="sm" onClick={onDelete}>
            <Trash2 className="mr-2 size-4" />
            Delete
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Category</span>
          <span className="font-medium capitalize">{template.category}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Source Type</span>
          <span className="font-medium capitalize">{template.source_type}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Usage</span>
          <span className="font-medium">{template.usage_count}</span>
        </div>
        {template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.tags.map((tag) => (
              <Badge key={tag} variant="outline">
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface ConfirmDeleteDialogProps {
  template: TemplateResponse | null
  onCancel: () => void
  onConfirm: () => Promise<void> | void
  isPending?: boolean
}

function ConfirmDeleteDialog({ template, onCancel, onConfirm, isPending }: ConfirmDeleteDialogProps) {
  return (
    <Dialog open={Boolean(template)} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete template</DialogTitle>
          <DialogDescription>
            This action cannot be undone. This will permanently delete the template{' '}
            <strong>{template?.name}</strong>.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={() => onConfirm()} disabled={isPending}>
            {isPending && <Loader2 className="mr-2 size-4 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
