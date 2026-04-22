export type ThemeVariantKey = 'default' | 'research' | 'nightly'

export const themeVariants: Record<
  ThemeVariantKey,
  {
    hero: string
    card: string
    accent: string
  }
> = {
  default: {
    hero: 'from-sidebar-primary/20 via-accent/20 to-secondary/30',
    card: 'bg-card',
    accent: 'text-sidebar-primary',
  },
  research: {
    hero: 'from-sidebar-primary/30 via-primary/10 to-accent/20',
    card: 'bg-card/90 backdrop-blur',
    accent: 'text-primary',
  },
  nightly: {
    hero: 'from-gray-900 via-slate-800 to-gray-900',
    card: 'bg-gray-900/70 backdrop-blur',
    accent: 'text-gray-300',
  },
}

export function getThemeVariant(key: ThemeVariantKey = 'default') {
  return themeVariants[key] ?? themeVariants.default
}
