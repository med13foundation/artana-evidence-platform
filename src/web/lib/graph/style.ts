export interface NodeVisualStyle {
  fillColor: string
  borderColor: string
  shape:
    | 'ellipse'
    | 'round-rectangle'
    | 'diamond'
    | 'hexagon'
    | 'triangle'
}

export interface EdgeVisualStyle {
  color: string
  opacity: number
  lineStyle: 'solid' | 'dashed' | 'dotted'
}

const DEFAULT_NODE_STYLE: NodeVisualStyle = {
  fillColor: '#3f5f78',
  borderColor: '#1e293b',
  shape: 'ellipse',
}

const DEFAULT_EDGE_STYLE: EdgeVisualStyle = {
  color: '#64748b',
  opacity: 0.42,
  lineStyle: 'solid',
}

function normalize(value: string): string {
  return value.trim().toUpperCase()
}

export function nodeVisualForEntityType(entityType: string): NodeVisualStyle {
  const normalized = normalize(entityType)

  if (normalized.includes('GENE')) {
    return {
      fillColor: '#0f766e',
      borderColor: '#134e4a',
      shape: 'round-rectangle',
    }
  }
  if (normalized.includes('PHENOTYPE')) {
    return {
      fillColor: '#2563eb',
      borderColor: '#1d4ed8',
      shape: 'ellipse',
    }
  }
  if (normalized.includes('VARIANT')) {
    return {
      fillColor: '#9333ea',
      borderColor: '#7e22ce',
      shape: 'diamond',
    }
  }
  if (normalized.includes('DISEASE')) {
    return {
      fillColor: '#d97706',
      borderColor: '#92400e',
      shape: 'hexagon',
    }
  }
  if (normalized.includes('PAPER') || normalized.includes('PUBLICATION')) {
    return {
      fillColor: '#dbeafe',
      borderColor: '#3b82f6',
      shape: 'hexagon',
    }
  }
  if (normalized.includes('DATASET') || normalized.includes('COHORT')) {
    return {
      fillColor: '#dcfce7',
      borderColor: '#16a34a',
      shape: 'diamond',
    }
  }
  if (normalized.includes('BIOCHEMICAL')) {
    return {
      fillColor: '#0ea5a4',
      borderColor: '#0f766e',
      shape: 'hexagon',
    }
  }
  if (normalized.includes('TAXON') || normalized.includes('MICROBIAL')) {
    return {
      fillColor: '#14b8a6',
      borderColor: '#0f766e',
      shape: 'triangle',
    }
  }

  return DEFAULT_NODE_STYLE
}

export function edgeVisualForStatus(curationStatus: string): EdgeVisualStyle {
  const normalized = normalize(curationStatus)

  if (normalized === 'APPROVED') {
    return {
      color: '#0f766e',
      opacity: 0.9,
      lineStyle: 'solid',
    }
  }
  if (normalized === 'UNDER_REVIEW') {
    return {
      color: '#0f9da0',
      opacity: 0.68,
      lineStyle: 'solid',
    }
  }
  if (normalized === 'DRAFT') {
    return {
      color: '#6366f1',
      opacity: 0.46,
      lineStyle: 'dashed',
    }
  }
  if (normalized === 'REJECTED') {
    return {
      color: '#dc2626',
      opacity: 0.28,
      lineStyle: 'dashed',
    }
  }
  if (normalized === 'RETRACTED') {
    return {
      color: '#b91c1c',
      opacity: 0.2,
      lineStyle: 'dotted',
    }
  }

  return DEFAULT_EDGE_STYLE
}

export function edgeColorForRelationType(relationType: string): string {
  const normalized = normalize(relationType)

  if (
    normalized.includes('REGULAT') ||
    normalized.includes('ACTIVAT') ||
    normalized.includes('INHIBIT') ||
    normalized.includes('SIGNAL')
  ) {
    return '#2563eb'
  }
  if (
    normalized.includes('ASSOCIATED') ||
    normalized.includes('DISEASE') ||
    normalized.includes('PHENOTYPE')
  ) {
    return '#c2410c'
  }
  if (
    normalized.includes('INTERACT') ||
    normalized.includes('BINDS') ||
    normalized.includes('COMPLEX')
  ) {
    return '#7c3aed'
  }
  if (
    normalized.includes('PATHWAY') ||
    normalized.includes('PROCESS') ||
    normalized.includes('FUNCTION')
  ) {
    return '#0f766e'
  }
  if (
    normalized.includes('CO_OCCURS') ||
    normalized.includes('POSSIBLE')
  ) {
    return '#0ea5a4'
  }
  if (
    normalized.includes('SUPPORTED_BY') ||
    normalized.includes('DERIVED_FROM')
  ) {
    return '#0ea5e9'
  }

  return '#475569'
}

export function edgeWidthForConfidence(confidence: number): number {
  if (confidence >= 0.95) {
    return 6.2
  }
  if (confidence >= 0.85) {
    return 5.2
  }
  if (confidence >= 0.7) {
    return 4.2
  }
  if (confidence >= 0.5) {
    return 3.1
  }
  return 2.2
}

export function edgeOpacityForConfidence(confidence: number): number {
  return Math.max(0.22, Math.min(0.96, 0.2 + confidence * 0.76))
}

export function edgeStrengthScore(confidence: number, sourceCount: number): number {
  const boundedConfidence = Math.max(0, Math.min(1, confidence))
  const evidenceBoost = Math.min(0.22, Math.log10(Math.max(1, sourceCount) + 1) * 0.16)
  return boundedConfidence + evidenceBoost
}

export function edgeWidthForStrength(confidence: number, sourceCount: number): number {
  const confidenceWidth = edgeWidthForConfidence(confidence)
  const evidenceLift = Math.min(0.55, Math.log10(Math.max(1, sourceCount) + 1) * 0.32)
  return Number((confidenceWidth + evidenceLift).toFixed(2))
}
