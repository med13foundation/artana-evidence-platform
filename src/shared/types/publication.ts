// Publication Types (placeholder)
export interface Publication {
  id: string
  title: string
  authors: string[]
  journal?: string
  year?: number
  doi?: string
  pmId?: string
  createdAt: string
  updatedAt: string
}
