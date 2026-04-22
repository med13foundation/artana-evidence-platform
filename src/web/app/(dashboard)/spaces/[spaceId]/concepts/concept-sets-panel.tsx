'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'

import { createConceptSetAction } from '@/app/actions/concepts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import type { ConceptSetResponse } from '@/types/concepts'

interface ConceptSetsPanelProps {
  spaceId: string
  canEdit: boolean
  conceptSets: ConceptSetResponse[]
  error?: string | null
}

interface ConceptSetFormState {
  name: string
  slug: string
  domainContext: string
  description: string
  sourceRef: string
}

const DEFAULT_FORM: ConceptSetFormState = {
  name: '',
  slug: '',
  domainContext: 'general',
  description: '',
  sourceRef: '',
}

function toSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

export function ConceptSetsPanel({
  spaceId,
  canEdit,
  conceptSets,
  error,
}: ConceptSetsPanelProps) {
  const router = useRouter()
  const [form, setForm] = useState<ConceptSetFormState>(DEFAULT_FORM)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleCreate = async () => {
    if (!canEdit) {
      toast.error('You do not have permission to create concept sets.')
      return
    }

    const name = form.name.trim()
    const slug = (form.slug.trim() || toSlug(name)).trim()
    const domainContext = form.domainContext.trim()

    if (!name || !slug || !domainContext) {
      toast.error('Name, slug, and domain context are required.')
      return
    }

    setIsSubmitting(true)
    const result = await createConceptSetAction(spaceId, {
      name,
      slug,
      domain_context: domainContext,
      description: form.description.trim() || null,
      source_ref: form.sourceRef.trim() || null,
    })
    setIsSubmitting(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Concept set created')
    setForm(DEFAULT_FORM)
    router.refresh()
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Create Concept Set</CardTitle>
          <CardDescription>
            Define a scoped concept namespace for this research space.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="concept-set-name">Name</Label>
            <Input
              id="concept-set-name"
              placeholder="MED13 discovery concepts"
              value={form.name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  name: event.target.value,
                  slug: current.slug.length > 0 ? current.slug : toSlug(event.target.value),
                }))
              }
              disabled={!canEdit}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-set-slug">Slug</Label>
            <Input
              id="concept-set-slug"
              placeholder="artana-discovery-concepts"
              value={form.slug}
              onChange={(event) => setForm((current) => ({ ...current, slug: toSlug(event.target.value) }))}
              disabled={!canEdit}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-set-domain-context">Domain Context</Label>
            <Input
              id="concept-set-domain-context"
              placeholder="biomedical"
              value={form.domainContext}
              onChange={(event) => setForm((current) => ({ ...current, domainContext: event.target.value }))}
              disabled={!canEdit}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="concept-set-source-ref">Source Ref (optional)</Label>
            <Input
              id="concept-set-source-ref"
              placeholder="run:2026-03-03T14:22Z"
              value={form.sourceRef}
              onChange={(event) => setForm((current) => ({ ...current, sourceRef: event.target.value }))}
              disabled={!canEdit}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="concept-set-description">Description (optional)</Label>
            <Textarea
              id="concept-set-description"
              rows={3}
              placeholder="What this concept set should capture"
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              disabled={!canEdit}
            />
          </div>
          <div className="md:col-span-2">
            <Button onClick={() => void handleCreate()} disabled={!canEdit || isSubmitting}>
              <Plus className="mr-2 size-4" />
              Create Concept Set
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Concept Sets</CardTitle>
          <CardDescription>
            {error ? <span className="text-destructive">{error}</span> : `${conceptSets.length} total`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? null : conceptSets.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              No concept sets found.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conceptSets.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <p className="font-medium text-foreground">{item.name}</p>
                      {item.description ? (
                        <p className="text-xs text-muted-foreground">{item.description}</p>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{item.slug}</TableCell>
                    <TableCell>{item.domain_context}</TableCell>
                    <TableCell>
                      <Badge variant={item.review_status === 'ACTIVE' ? 'default' : 'secondary'}>
                        {item.review_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(item.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
