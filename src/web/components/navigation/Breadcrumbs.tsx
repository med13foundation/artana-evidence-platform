"use client"

import Link from 'next/link'
import { ChevronRight, Home } from 'lucide-react'
import { usePathname } from 'next/navigation'

interface BreadcrumbItem {
  label: string
  href?: string
}

export function Breadcrumbs() {
  const pathname = usePathname()

  // Skip breadcrumbs on auth pages
  if (pathname.startsWith('/auth')) {
    return null
  }

  const pathSegments = pathname.split('/').filter(Boolean)
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Home', href: '/dashboard' },
  ]

  // Build breadcrumbs from path segments
  let currentPath = ''
  pathSegments.forEach((segment, index) => {
    // Skip "spaces" segment - don't show "Research Spaces" in breadcrumbs
    if (segment === 'spaces') {
      currentPath += `/${segment}`
      return
    }

    currentPath += `/${segment}`
    const isLast = index === pathSegments.length - 1

    // Format label
    let label = segment
    if (segment === 'new') {
      label = 'New'
    } else if (segment.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
      // UUID - could fetch name, but for now just show "Details"
      label = 'Details'
    } else {
      // Capitalize first letter
      label = segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, ' ')
    }

    breadcrumbs.push({
      label,
      href: isLast ? undefined : currentPath,
    })
  })

  if (breadcrumbs.length <= 1) {
    return null
  }

  return (
    <nav className="mb-4 flex items-center space-x-2 text-sm text-muted-foreground">
      {breadcrumbs.map((crumb, index) => (
        <div key={crumb.href || index} className="flex items-center space-x-2">
          {index === 0 ? (
            <Link
              href={crumb.href || '#'}
              className="transition-colors hover:text-foreground"
            >
              <Home className="size-4" />
            </Link>
          ) : (
            <>
              <ChevronRight className="size-4" />
              {crumb.href ? (
                <Link
                  href={crumb.href}
                  className="transition-colors hover:text-foreground"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span className="font-medium text-foreground">{crumb.label}</span>
              )}
            </>
          )}
        </div>
      ))}
    </nav>
  )
}
