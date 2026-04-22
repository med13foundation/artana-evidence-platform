import Image from 'next/image'
import { BRAND_LOGO_DARK_SRC, BRAND_LOGO_LIGHT_SRC } from '@/lib/branding'
import { cn } from '@/lib/utils'

interface BrandLogoProps {
  alt: string
  width: number
  height: number
  className?: string
  priority?: boolean
}

export function BrandLogo({
  alt,
  width,
  height,
  className,
  priority = false,
}: BrandLogoProps) {
  return (
    <>
      <Image
        src={BRAND_LOGO_LIGHT_SRC}
        alt={alt}
        width={width}
        height={height}
        className={cn('dark:hidden', className)}
        style={{ height: 'auto' }}
        priority={priority}
        unoptimized
      />
      <Image
        src={BRAND_LOGO_DARK_SRC}
        alt={alt}
        width={width}
        height={height}
        className={cn('hidden dark:block', className)}
        style={{ height: 'auto' }}
        priority={priority}
        unoptimized
      />
    </>
  )
}
