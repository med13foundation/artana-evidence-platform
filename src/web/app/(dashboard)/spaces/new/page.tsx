"use client"

import { CreateSpaceForm } from '@/components/research-spaces/CreateSpaceForm'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHero } from '@/components/ui/composition-patterns'

export default function NewSpacePage() {
  return (
    <div className="space-y-6">
      <PageHero
        title="Create Research Space"
        description="Spin up a secure workspace where curators, researchers, and administrators can collaborate on MED13 data."
        variant="research"
      />
      <div className="max-w-3xl">
        <Card>
          <CardHeader>
            <CardTitle>Space Details</CardTitle>
            <CardDescription>
              Define the foundational information, slug, and governance settings for the new space.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CreateSpaceForm />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
