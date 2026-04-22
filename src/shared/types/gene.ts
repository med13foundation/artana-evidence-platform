import { z } from 'zod'

// Gene Types (aligned with existing domain entities)
export interface Gene {
  id: string
  symbol: string
  name?: string
  aliases?: string[]
  chromosome?: string
  startPosition?: number
  endPosition?: number
  strand?: '+' | '-'
  geneType?: string
  description?: string
  createdAt: string
  updatedAt: string
}

export interface GeneSearchResult {
  gene: Gene
  score?: number
  highlights?: Record<string, string[]>
}

export const GeneSchema = z.object({
  id: z.string().uuid(),
  symbol: z.string().min(1),
  name: z.string().optional(),
  aliases: z.array(z.string()).optional(),
  chromosome: z.string().optional(),
  startPosition: z.number().int().positive().optional(),
  endPosition: z.number().int().positive().optional(),
  strand: z.enum(['+', '-']).optional(),
  geneType: z.string().optional(),
  description: z.string().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})
