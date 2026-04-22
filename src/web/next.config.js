const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL?.trim() || ''
const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL?.trim() || ''

const isLocalApiUrl = (value) =>
  value.startsWith('http://localhost') || value.startsWith('https://localhost')

const isLocalWsUrl = (value) =>
  value.startsWith('ws://localhost') || value.startsWith('wss://localhost')

const buildCspHeader = () => {
  const isDevelopment = process.env.NODE_ENV === 'development'
  const connectSources = new Set(["'self'"])
  if (API_BASE_URL && (isDevelopment || !isLocalApiUrl(API_BASE_URL))) {
    connectSources.add(API_BASE_URL)
  }
  if (WS_BASE_URL && (isDevelopment || !isLocalWsUrl(WS_BASE_URL))) {
    connectSources.add(WS_BASE_URL)
  }

  if (isDevelopment) {
    connectSources.add('http://localhost:8080')
    connectSources.add('ws://localhost:8080')
    connectSources.add('ws://localhost:3000')
  } else {
    // Keep production connect-src resilient even when build-time public URLs are not injected.
    connectSources.add('https:')
    connectSources.add('wss:')
  }
  // Enhanced CSP for better security
  // Note: 'unsafe-inline' and 'unsafe-eval' are required for Next.js HMR and some features
  // In production, consider using nonces or hashes for stricter CSP
  const cspDirectives = [
    "default-src 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data: https:",
    "object-src 'none'",
    // Next.js requires 'unsafe-inline' for styles and 'unsafe-eval' for HMR
    // Consider using nonces in production for stricter security
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    `connect-src ${Array.from(connectSources).join(' ')}`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    // Prevent base tag injection attacks
    "base-uri 'self'",
    // Prevent form action hijacking
    "form-action 'self'",
  ]

  // Upgrade insecure requests only in production
  if (!isDevelopment) {
    cspDirectives.push("upgrade-insecure-requests")
  }

  return cspDirectives.join('; ')
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  // Suppress font warnings
  logging: {
    fetches: {
      fullUrl: false,
    },
  },
  // Webpack configuration
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
      }
    }
    return config
  },
  // Suppress specific Next.js warnings
  onDemandEntries: {
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
  // Configure headers for security
  async headers() {
    const cspHeader = buildCspHeader()
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin',
          },
          {
            key: 'Content-Security-Policy',
            value: cspHeader,
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
        ],
      },
    ]
  },
  // Configure images for external domains if needed
  images: {
    dangerouslyAllowSVG: true,
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
    domains: ['localhost'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },
  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: API_BASE_URL,
    NEXT_PUBLIC_WS_URL: WS_BASE_URL,
  },
}

module.exports = nextConfig
