"use client"

import { useRouter } from 'next/navigation'
import { RefreshCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  DictionaryEntityTypeListResponse,
  DictionaryRelationTypeListResponse,
  EntityResolutionPolicyListResponse,
  RelationConstraintListResponse,
  TransformRegistryListResponse,
  VariableDefinitionListResponse,
} from '@/types/dictionary'

import { CreateVariableCard } from './variable-create-card'
import { VariablesTableCard } from './variables-table-card'
import { TransformsTableCard } from './transforms-table-card'
import { PoliciesTableCard } from './policies-table-card'
import { ConstraintsTableCard } from './constraints-table-card'
import { EntityTypesTableCard } from './entity-types-table-card'
import { RelationTypesTableCard } from './relation-types-table-card'
import { DictionaryCurationCard } from './dictionary-curation-card'

interface DictionaryClientData {
  variables: VariableDefinitionListResponse | null
  transforms: TransformRegistryListResponse | null
  policies: EntityResolutionPolicyListResponse | null
  constraints: RelationConstraintListResponse | null
  entityTypes: DictionaryEntityTypeListResponse | null
  relationTypes: DictionaryRelationTypeListResponse | null
}

interface DictionaryClientErrors {
  variables?: string | null
  transforms?: string | null
  policies?: string | null
  constraints?: string | null
  entityTypes?: string | null
  relationTypes?: string | null
}

interface DictionaryClientProps {
  data: DictionaryClientData
  errors: DictionaryClientErrors
}

export default function DictionaryClient({
  data,
  errors,
}: DictionaryClientProps) {
  const router = useRouter()

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">Dictionary</h1>
          <p className="text-sm text-muted-foreground">
            Manage the kernel dictionary: variables, transforms, resolution policies, and relation constraints.
          </p>
        </div>
        <Button variant="outline" onClick={() => router.refresh()} className="w-full sm:w-auto">
          <RefreshCcw className="mr-2 size-4" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="variables">
        <TabsList>
          <TabsTrigger value="variables">Variables</TabsTrigger>
          <TabsTrigger value="entity-types">Entity Types</TabsTrigger>
          <TabsTrigger value="relation-types">Relation Types</TabsTrigger>
          <TabsTrigger value="curation">Curation</TabsTrigger>
          <TabsTrigger value="transforms">Transforms</TabsTrigger>
          <TabsTrigger value="policies">Resolution Policies</TabsTrigger>
          <TabsTrigger value="constraints">Relation Constraints</TabsTrigger>
        </TabsList>

        <TabsContent value="variables" className="mt-4 space-y-4">
          <CreateVariableCard />
          <VariablesTableCard variables={data.variables} error={errors.variables} />
        </TabsContent>

        <TabsContent value="entity-types" className="mt-4">
          <EntityTypesTableCard
            entityTypes={data.entityTypes}
            error={errors.entityTypes}
          />
        </TabsContent>

        <TabsContent value="relation-types" className="mt-4">
          <RelationTypesTableCard
            relationTypes={data.relationTypes}
            error={errors.relationTypes}
          />
        </TabsContent>

        <TabsContent value="curation" className="mt-4">
          <DictionaryCurationCard
            variables={data.variables?.variables ?? []}
            entityTypes={data.entityTypes?.entity_types ?? []}
            relationTypes={data.relationTypes?.relation_types ?? []}
          />
        </TabsContent>

        <TabsContent value="transforms" className="mt-4">
          <TransformsTableCard transforms={data.transforms} error={errors.transforms} />
        </TabsContent>

        <TabsContent value="policies" className="mt-4">
          <PoliciesTableCard policies={data.policies} error={errors.policies} />
        </TabsContent>

        <TabsContent value="constraints" className="mt-4">
          <ConstraintsTableCard constraints={data.constraints} error={errors.constraints} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
