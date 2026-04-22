import * as GraphClient from '@/lib/api/graph-client'
import { fetchSpaceConceptSets } from '@/lib/api/concepts'
import { fetchDictionaryVariables } from '@/lib/api/dictionary'
import { resolveGraphApiBaseUrl } from '@/lib/api/graph-base-url'
import { fetchKernelEntities } from '@/lib/api/kernel'

describe('graph client api barrel', () => {
  it('re-exports kernel graph helpers', () => {
    expect(GraphClient.fetchKernelEntities).toBe(fetchKernelEntities)
  })

  it('re-exports concept graph helpers', () => {
    expect(GraphClient.fetchSpaceConceptSets).toBe(fetchSpaceConceptSets)
  })

  it('re-exports dictionary graph helpers', () => {
    expect(GraphClient.fetchDictionaryVariables).toBe(fetchDictionaryVariables)
  })

  it('re-exports graph base-url resolution', () => {
    expect(GraphClient.resolveGraphApiBaseUrl).toBe(resolveGraphApiBaseUrl)
  })
})
