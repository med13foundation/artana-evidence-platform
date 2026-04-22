import type { HypothesisResponse } from '@/types/kernel'

export const ALL_FILTER_VALUE = '__all__'

export type HypothesisClaimStatus = 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
export type HypothesisCertaintyBand = 'HIGH' | 'MEDIUM' | 'LOW'

export function normalizeSeedIds(value: string): string[] {
  const rawValues = value
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)

  const seen = new Set<string>()
  const normalized: string[] = []
  for (const rawValue of rawValues) {
    const lower = rawValue.toLowerCase()
    if (seen.has(lower)) {
      continue
    }
    seen.add(lower)
    normalized.push(rawValue)
  }
  return normalized
}

export function confidenceBand(value: number): HypothesisCertaintyBand {
  if (value >= 0.8) {
    return 'HIGH'
  }
  if (value >= 0.6) {
    return 'MEDIUM'
  }
  return 'LOW'
}

export function confidencePercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

export function humanizeToken(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function statusBadgeVariant(
  status: HypothesisClaimStatus,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'RESOLVED') return 'default'
  if (status === 'REJECTED') return 'destructive'
  if (status === 'NEEDS_MAPPING') return 'secondary'
  return 'outline'
}

export function filterHypotheses(
  hypotheses: HypothesisResponse[],
  originFilter: string,
  statusFilter: string,
  certaintyFilter: string,
): HypothesisResponse[] {
  return hypotheses.filter((hypothesis) => {
    if (originFilter !== ALL_FILTER_VALUE && hypothesis.origin !== originFilter) {
      return false
    }
    if (statusFilter !== ALL_FILTER_VALUE && hypothesis.claim_status !== statusFilter) {
      return false
    }
    if (certaintyFilter !== ALL_FILTER_VALUE) {
      const candidateBand = confidenceBand(hypothesis.confidence)
      if (candidateBand !== certaintyFilter) {
        return false
      }
    }
    return true
  })
}
