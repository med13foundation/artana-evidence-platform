import type { ReactNode } from 'react'

export function parseRelationThresholds(value: string): Record<string, number> {
  const entries = value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)

  const thresholds: Record<string, number> = {}
  for (const entry of entries) {
    const [rawRelationType, rawThreshold] = entry.split('=', 2)
    if (!rawRelationType || !rawThreshold) {
      continue
    }
    const relationType = rawRelationType.trim().toUpperCase()
    const threshold = Number(rawThreshold.trim())
    if (!relationType || Number.isNaN(threshold)) {
      continue
    }
    thresholds[relationType] = Math.max(0, Math.min(1, threshold))
  }
  return thresholds
}

export function CardSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="space-y-4 rounded-md border p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="space-y-4">{children}</div>
    </section>
  )
}
