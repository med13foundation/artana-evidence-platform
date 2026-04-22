import type { Metadata } from 'next'
import { Inter, Nunito_Sans, Playfair_Display } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/components/query-provider'
import { ThemeProvider } from '@/components/theme-provider'
import { SessionProvider } from '@/components/session-provider'
import { Toaster } from '@/components/ui/toaster'
import {
  ADMIN_APP_DESCRIPTION,
  ADMIN_BRAND_NAME,
  BRAND_LOGO_DARK_SRC,
  BRAND_LOGO_LIGHT_SRC,
} from '@/lib/branding'
import { getServerSession } from 'next-auth'
import { authOptions, isRecoverableSessionDecryptionError } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-body',
  adjustFontFallback: true,
  fallback: ['system-ui', 'arial'],
})

const nunitoSans = Nunito_Sans({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-heading',
  weight: ['400', '600', '700', '800'],
  adjustFontFallback: false,
  fallback: ['system-ui', 'arial'],
  preload: true,
})

const playfairDisplay = Playfair_Display({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-display',
  adjustFontFallback: true,
  fallback: ['Georgia', 'serif'],
})

export const metadata: Metadata = {
  title: ADMIN_BRAND_NAME,
  description: ADMIN_APP_DESCRIPTION,
  icons: {
    icon: [
      { url: BRAND_LOGO_LIGHT_SRC, media: '(prefers-color-scheme: light)' },
      { url: BRAND_LOGO_DARK_SRC, media: '(prefers-color-scheme: dark)' },
    ],
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  let session = null
  try {
    session = await getServerSession(authOptions)
  } catch (error) {
    if (!isRecoverableSessionDecryptionError(error)) {
      throw error
    }
  }

  return (
    <html lang="en" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className={`${inter.variable} ${nunitoSans.variable} ${playfairDisplay.variable} ${inter.className}`} suppressHydrationWarning>
        <SessionProvider session={session}>
          <QueryProvider>
            <ThemeProvider
              attribute="class"
              defaultTheme="light"
              enableSystem
              disableTransitionOnChange
            >
              {children}
              <Toaster />
            </ThemeProvider>
          </QueryProvider>
        </SessionProvider>
      </body>
    </html>
  )
}
