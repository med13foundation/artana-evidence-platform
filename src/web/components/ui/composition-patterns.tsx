"use client"

import type { ReactNode } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { getThemeVariant, type ThemeVariantKey } from '@/lib/theme/variants'

export interface StatCardProps {
  title: string
  value: ReactNode
  description?: ReactNode
  icon?: ReactNode
  isLoading?: boolean
  footer?: ReactNode
}

export function StatCard({
  title,
  value,
  description,
  icon,
  isLoading = false,
  footer,
}: StatCardProps) {
  return (
    <Card className="h-full shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="font-heading text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {isLoading ? <span className="text-muted-foreground">—</span> : value}
        </div>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
        {footer && <div className="mt-3">{footer}</div>}
      </CardContent>
    </Card>
  )
}

export interface DashboardSectionProps {
  title: string
  description?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}

export function DashboardSection({
  title,
  description,
  actions,
  children,
  className,
}: DashboardSectionProps) {
  return (
    <Card className={cn('h-full shadow-brand-sm border-card-border rounded-2xl', className)}>
      <CardHeader className="space-y-1.5 pb-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="section-heading !text-2xl">{title}</CardTitle>
            {description && (
              <CardDescription className="mt-1.5 text-base">{description}</CardDescription>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export function SectionGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
      {children}
    </div>
  )
}

interface PageHeroProps {
  title: string
  description?: string
  eyebrow?: string
  actions?: ReactNode
  variant?: ThemeVariantKey
  className?: string
}

export function PageHero({
  title,
  description,
  eyebrow,
  actions,
  variant = 'default',
  className,
}: PageHeroProps) {
  const theme = getThemeVariant(variant)
  return (
    <div
      className={cn(
        'mb-brand-lg rounded-3xl border border-brand-primary/10 p-brand-md sm:p-brand-lg bg-gradient-to-br from-brand-primary/5 via-background to-brand-secondary/5 text-foreground relative overflow-hidden shadow-brand-sm',
        theme.hero,
        className,
      )}
    >
      <div className="absolute right-0 top-0 -mr-20 -mt-20 size-64 rounded-full bg-brand-primary/5 blur-3xl" />
      <div className="absolute bottom-0 left-0 -mb-20 -ml-20 size-64 rounded-full bg-brand-secondary/5 blur-3xl" />

      <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          {eyebrow && (
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.4em] text-muted-foreground/70">
              {eyebrow}
            </p>
          )}
          <h1 className="hero-heading">{title}</h1>
          {description && (
            <p className="body-large mt-4 max-w-2xl text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="shrink-0">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
