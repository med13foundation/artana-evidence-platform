import type { DataSource } from '@/types/data-source'

const CLINVAR_CATALOG_ENTRY_IDS = new Set(['clinvar', 'clinvar_benchmark'])

export const DEFAULT_CLINVAR_AGENT_PROMPT =
  'Use ClinVar-specific ontology and evidence criteria to generate targeted queries.'

export interface SourceAgentConfigSnapshot {
  isAiManaged: boolean
  queryAgentSourceType: string | null
  catalogEntryId: string | null
  isClinvarCatalogSource: boolean
  supportsAiControls: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

export function getSourceAgentConfigSnapshot(
  source: DataSource,
): SourceAgentConfigSnapshot {
  const config = isRecord(source.config) ? source.config : {}
  const metadata = isRecord(config.metadata) ? config.metadata : {}
  const agentConfig = isRecord(metadata.agent_config) ? metadata.agent_config : {}

  const catalogEntryId = normalizeNonEmptyString(metadata.catalog_entry_id)
  const normalizedCatalogEntryId = catalogEntryId?.toLowerCase() ?? null
  const isClinvarCatalogSource =
    normalizedCatalogEntryId !== null &&
    CLINVAR_CATALOG_ENTRY_IDS.has(normalizedCatalogEntryId)

  const queryAgentSourceType =
    normalizeNonEmptyString(agentConfig.query_agent_source_type) ??
    (isClinvarCatalogSource ? 'clinvar' : null)

  const isAiManaged =
    agentConfig.is_ai_managed === true ||
    (isClinvarCatalogSource && queryAgentSourceType !== null)

  const supportsAiControls =
    source.source_type === 'pubmed' || queryAgentSourceType !== null || isAiManaged

  return {
    isAiManaged,
    queryAgentSourceType,
    catalogEntryId: normalizedCatalogEntryId,
    isClinvarCatalogSource,
    supportsAiControls,
  }
}
