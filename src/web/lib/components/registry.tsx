"use client"

import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'

type ComponentFactory<Props> = (props: Props) => ReactNode

class ComponentRegistry {
  private registry = new Map<string, ComponentFactory<unknown>>()

  register<Props>(key: string, component: ComponentFactory<Props>) {
    this.registry.set(key, component as ComponentFactory<unknown>)
  }

  get<Props>(key: string): ComponentFactory<Props> | undefined {
    return this.registry.get(key) as ComponentFactory<Props> | undefined
  }
}

export const componentRegistry = new ComponentRegistry()

const statusColors: Record<string, string> = {
  active: 'bg-green-500',
  inactive: 'bg-gray-500',
  draft: 'bg-yellow-500',
  error: 'bg-red-500',
  pending_review: 'bg-blue-500',
  archived: 'bg-gray-400',
  default: 'bg-gray-500',
}

componentRegistry.register<{ status: string }>(
  'dataSource.statusBadge',
  ({ status }) => (
    <Badge className={`${statusColors[status] ?? statusColors.default} text-white`}>
      {status}
    </Badge>
  ),
)

export type { ComponentFactory }
