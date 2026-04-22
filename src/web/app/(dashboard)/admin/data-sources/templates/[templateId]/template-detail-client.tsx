"use client"

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TemplateDialog } from '@/components/templates/TemplateDialog'
import { ValidationRulesDialog } from '@/components/templates/ValidationRulesDialog'
import { useState } from 'react'
import {
  approveTemplateAction,
  deleteTemplateAction,
  publishTemplateAction,
  updateTemplateAction,
} from '@/app/actions/templates'
import { Loader2, ArrowLeft, Pencil, Trash2, ShieldCheck, Eye } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { TemplateResponse, TemplateUpdatePayload, TemplateValidationRule } from '@/types/template'

interface TemplateDetailClientProps {
  templateId: string
  template: TemplateResponse | null
}

export default function TemplateDetailClient({ templateId, template }: TemplateDetailClientProps) {
  const router = useRouter()
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [rulesDialogOpen, setRulesDialogOpen] = useState(false)
  const [rulesSaving, setRulesSaving] = useState(false)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [publishLoading, setPublishLoading] = useState(false)

  const handleDelete = async () => {
    setDeleteLoading(true)
    try {
      const result = await deleteTemplateAction(templateId)
      if (!result.success) {
        throw new Error(result.error)
      }
      router.push('/admin/data-sources/templates')
    } finally {
      setDeleteLoading(false)
      setDeleteOpen(false)
    }
  }

  const handleUpdate = async (payload: TemplateUpdatePayload['data']) => {
    const result = await updateTemplateAction({ templateId, data: payload })
    if (!result.success) {
      throw new Error(result.error)
    }
    router.refresh()
    setEditOpen(false)
  }

  const handleValidationRulesSave = async (rules: TemplateValidationRule[]) => {
    setRulesSaving(true)
    try {
      const result = await updateTemplateAction({ templateId, data: { validation_rules: rules } })
      if (!result.success) {
        throw new Error(result.error)
      }
      router.refresh()
    } finally {
      setRulesSaving(false)
    }
  }

  const handleApprove = async () => {
    setApprovalLoading(true)
    try {
      const result = await approveTemplateAction(templateId)
      if (!result.success) {
        throw new Error(result.error)
      }
      router.refresh()
    } finally {
      setApprovalLoading(false)
    }
  }

  const handlePublish = async () => {
    setPublishLoading(true)
    try {
      const result = await publishTemplateAction(templateId)
      if (!result.success) {
        throw new Error(result.error)
      }
      router.refresh()
    } finally {
      setPublishLoading(false)
    }
  }

  if (!template) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          Failed to load template.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" asChild className="mb-2">
            <Link href="/admin/data-sources/templates">
              <ArrowLeft className="mr-2 size-4" />
              Back to Templates
            </Link>
          </Button>
          <h1 className="font-heading text-2xl font-bold">{template.name}</h1>
          <p className="text-muted-foreground">{template.description || 'No description provided.'}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setEditOpen(true)}>
            <Pencil className="mr-2 size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="mr-2 size-4" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
            <CardDescription>Template classification and usage</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <DetailRow label="Category" value={template.category} />
            <DetailRow label="Source Type" value={template.source_type} />
            <DetailRow label="Usage Count" value={String(template.usage_count)} />
            <DetailRow label="Success Rate" value={`${Math.round(template.success_rate * 100)}%`} />
            <DetailRow label="Visibility" value={template.is_public ? 'Public' : 'Private'} />
            {template.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {template.tags.map((tag) => (
                  <Badge key={tag} variant="outline">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Schema Definition</CardTitle>
            <CardDescription>Current JSON schema for this template.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded-md bg-muted p-4 text-xs">
              {JSON.stringify(template.schema_definition, null, 2)}
            </pre>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Validation Rules</CardTitle>
              <CardDescription>Field-level validation enforced before ingestion.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => setRulesDialogOpen(true)}>
              Edit Rules
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {template.validation_rules.length === 0 ? (
              <p className="text-muted-foreground">No validation rules defined.</p>
            ) : (
              <div className="space-y-3">
                {template.validation_rules.map((rule) => (
                  <div key={`${rule.field}-${rule.rule_type}`} className="rounded-md border p-3">
                    <div className="flex items-center justify-between text-sm font-medium">
                      <span>{rule.field}</span>
                      <Badge variant="secondary">{rule.rule_type.replace('_', ' ')}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{rule.error_message}</p>
                    {rule.parameters && Object.keys(rule.parameters).length > 0 && (
                      <pre className="mt-2 rounded-md bg-muted p-2 text-[11px]">
                        {JSON.stringify(rule.parameters, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Approval & Visibility</CardTitle>
            <CardDescription>Manage publication and approval workflow.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="space-y-1">
              <DetailRow label="Approval Required" value={template.approval_required ? 'Yes' : 'No'} />
              <DetailRow label="Approval Status" value={template.is_approved ? 'Approved' : 'Pending review'} />
              <DetailRow label="Approved At" value={formatDate(template.approved_at)} />
              <DetailRow label="Created" value={formatDate(template.created_at)} />
              <DetailRow label="Updated" value={formatDate(template.updated_at)} />
              <DetailRow label="Visibility" value={template.is_public ? 'Public' : 'Private'} />
            </div>
            <div className="flex flex-col gap-3">
              <Button onClick={handleApprove} disabled={template.is_approved || approvalLoading} variant="secondary">
                {approvalLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
                <ShieldCheck className="mr-2 size-4" />
                Approve
              </Button>
              <Button onClick={handlePublish} disabled={template.is_public || publishLoading}>
                {publishLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
                <Eye className="mr-2 size-4" />
                Make Public
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <TemplateDialog mode="edit" open={editOpen} onOpenChange={setEditOpen} template={template} onUpdate={handleUpdate} />

      <ValidationRulesDialog
        open={rulesDialogOpen}
        onOpenChange={setRulesDialogOpen}
        rules={template.validation_rules}
        onSave={handleValidationRulesSave}
        isSaving={rulesSaving}
      />

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Template</DialogTitle>
            <DialogDescription>
              This cannot be undone. This will permanently delete <strong>{template.name}</strong>.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteLoading}>
              {deleteLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}

function formatDate(value?: string | null) {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}
