const toNonNegativeInt = (value: unknown): number | null => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null
  }
  return Math.max(Math.trunc(value), 0)
}

export const formatCheckpoint = (checkpoint?: Record<string, unknown> | null): string => {
  if (!checkpoint || Object.keys(checkpoint).length === 0) {
    return 'n/a'
  }
  return Object.entries(checkpoint)
    .slice(0, 2)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(', ')
}

export const formatRelevanceGateSummary = (
  checkpoint?: Record<string, unknown> | null,
): string | null => {
  if (!checkpoint) {
    return null
  }
  const preFiltered = toNonNegativeInt(checkpoint.pre_rescue_filtered_out_count)
  const postFiltered = toNonNegativeInt(checkpoint.filtered_out_count)
  const rescueAttempted = toNonNegativeInt(checkpoint.full_text_rescue_attempted_count)
  const rescued = toNonNegativeInt(checkpoint.full_text_rescued_count)
  if (
    preFiltered === null &&
    postFiltered === null &&
    rescueAttempted === null &&
    rescued === null
  ) {
    return null
  }
  return `Relevance pre/post ${preFiltered ?? 0}/${postFiltered ?? 0} · Rescue ${rescued ?? 0}/${rescueAttempted ?? 0}`
}
