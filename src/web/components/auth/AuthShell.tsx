"use client"

import type { ReactNode } from 'react'
import { BrandLogo } from '@/components/branding/BrandLogo'
import { Card, CardContent } from '@/components/ui/card'
import { BRAND_LOGO_ALT, BRAND_NAME } from '@/lib/branding'

interface AuthShellProps {
  title: string
  description: string
  children: ReactNode
  footer?: ReactNode
  isLoading?: boolean
}

export function AuthShell({ title, description, children, footer, isLoading = false }: AuthShellProps) {
  return (
    <div className="from-brand-primary/8 to-brand-secondary/8 flex min-h-screen items-center justify-center bg-gradient-to-br via-background px-4 py-8">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="flex flex-col items-center gap-3">
            <div className="flex aspect-square size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border/50 bg-white/90 shadow-sm dark:border-white/10 dark:bg-[#0F1C22]">
              <BrandLogo
                alt={BRAND_LOGO_ALT}
                width={48}
                height={48}
                className="size-12 object-contain"
                priority
              />
            </div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-muted-foreground/70">{BRAND_NAME}</p>
          </div>
          <h1 className="section-heading mt-3">{title}</h1>
          <p className="body-large mt-3 text-muted-foreground">{description}</p>
        </div>

        <Card className="border-border/60 bg-card/95 shadow-brand-lg backdrop-blur">
          <CardContent className="pt-6">
            {isLoading ? (
              <div className="py-6 text-center text-muted-foreground">Loading…</div>
            ) : (
              children
            )}
          </CardContent>
        </Card>

        {footer}
      </div>
    </div>
  )
}
