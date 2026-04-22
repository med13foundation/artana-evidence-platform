import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import DictionaryClient from './dictionary-client'
import {
  fetchDictionaryEntityTypes,
  fetchDictionaryRelationConstraints,
  fetchDictionaryRelationTypes,
  fetchDictionaryResolutionPolicies,
  fetchDictionaryTransforms,
  fetchDictionaryVariables,
} from '@/lib/api/dictionary'
import { UserRole } from '@/types/auth'
import type {
  EntityResolutionPolicyListResponse,
  DictionaryEntityTypeListResponse,
  DictionaryRelationTypeListResponse,
  RelationConstraintListResponse,
  TransformRegistryListResponse,
  VariableDefinitionListResponse,
} from '@/types/dictionary'

export default async function DictionaryPage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard?error=AdminOnly')
  }

  let variables: VariableDefinitionListResponse | null = null
  let variablesError: string | null = null
  let transforms: TransformRegistryListResponse | null = null
  let transformsError: string | null = null
  let policies: EntityResolutionPolicyListResponse | null = null
  let policiesError: string | null = null
  let constraints: RelationConstraintListResponse | null = null
  let constraintsError: string | null = null
  let entityTypes: DictionaryEntityTypeListResponse | null = null
  let entityTypesError: string | null = null
  let relationTypes: DictionaryRelationTypeListResponse | null = null
  let relationTypesError: string | null = null

  try {
    variables = await fetchDictionaryVariables({}, token)
  } catch (error) {
    variablesError = error instanceof Error ? error.message : 'Unable to load dictionary variables.'
    console.error('[DictionaryPage] Failed to fetch variables', error)
  }

  try {
    transforms = await fetchDictionaryTransforms({}, token)
  } catch (error) {
    transformsError = error instanceof Error ? error.message : 'Unable to load transform registry.'
    console.error('[DictionaryPage] Failed to fetch transforms', error)
  }

  try {
    policies = await fetchDictionaryResolutionPolicies(token)
  } catch (error) {
    policiesError = error instanceof Error ? error.message : 'Unable to load resolution policies.'
    console.error('[DictionaryPage] Failed to fetch resolution policies', error)
  }

  try {
    constraints = await fetchDictionaryRelationConstraints({}, token)
  } catch (error) {
    constraintsError = error instanceof Error ? error.message : 'Unable to load relation constraints.'
    console.error('[DictionaryPage] Failed to fetch relation constraints', error)
  }

  try {
    entityTypes = await fetchDictionaryEntityTypes({}, token)
  } catch (error) {
    entityTypesError = error instanceof Error ? error.message : 'Unable to load entity types.'
    console.error('[DictionaryPage] Failed to fetch entity types', error)
  }

  try {
    relationTypes = await fetchDictionaryRelationTypes({}, token)
  } catch (error) {
    relationTypesError = error instanceof Error ? error.message : 'Unable to load relation types.'
    console.error('[DictionaryPage] Failed to fetch relation types', error)
  }

  return (
    <DictionaryClient
      data={{
        variables,
        transforms,
        policies,
        constraints,
        entityTypes,
        relationTypes,
      }}
      errors={{
        variables: variablesError,
        transforms: transformsError,
        policies: policiesError,
        constraints: constraintsError,
        entityTypes: entityTypesError,
        relationTypes: relationTypesError,
      }}
    />
  )
}
