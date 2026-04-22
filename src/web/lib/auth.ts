import { NextAuthOptions, DefaultSession } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import { JWT } from "next-auth/jwt"
import axios, { AxiosHeaders } from "axios"
import { getCloudRunServiceAuthorization } from "@/lib/api/cloud-run-service-auth"

// Extend the built-in session types
declare module "next-auth" {
  interface Session extends DefaultSession {
    user: {
      id: string
      email: string
      username: string
      full_name: string
      role: string
      email_verified: boolean
      access_token: string
      expires_at: number
    } & DefaultSession["user"]
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    access_token: string
    refresh_token: string
    expires_at: number
    refresh_failed?: boolean
    user: {
      id: string
      email: string
      username: string
      full_name: string
      role: string
      email_verified: boolean
    }
  }
}

interface BackendUser {
  id: string
  email: string
  username: string
  full_name: string
  role: string
  email_verified: boolean
}

interface BackendLoginResponse {
  user: BackendUser
  access_token: string
  refresh_token: string
  expires_in: number
}

interface AuthenticatedUser extends BackendUser {
  access_token: string
  refresh_token: string
  expires_at: number
}

const LOCAL_API_BASE_URL = "http://localhost:8080"
const ADMIN_HOST_PREFIX = "artana-admin"
const API_HOST_PREFIX = "artana-resource-library"

function inferApiBaseUrlFromHostname(hostname: string): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const apiHostname = hostname.replace(ADMIN_HOST_PREFIX, API_HOST_PREFIX)
  return `https://${apiHostname}`
}

function inferApiBaseUrlFromNextAuthUrl(nextAuthUrl: string): string | null {
  try {
    const nextAuthHostname = new URL(nextAuthUrl).hostname
    return inferApiBaseUrlFromHostname(nextAuthHostname)
  } catch {
    return null
  }
}

function resolveAuthApiBaseUrl(): string {
  const runtimeApiUrl =
    process.env.API_BASE_URL || process.env.INTERNAL_API_URL
  if (typeof runtimeApiUrl === "string" && runtimeApiUrl.trim().length > 0) {
    return runtimeApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === "string" && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth = inferApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  const configuredPublicApiUrl = process.env.NEXT_PUBLIC_API_URL
  if (
    typeof configuredPublicApiUrl === "string" &&
    configuredPublicApiUrl.trim().length > 0
  ) {
    return configuredPublicApiUrl
  }

  return LOCAL_API_BASE_URL
}

// FastAPI backend URL
const API_BASE_URL = resolveAuthApiBaseUrl()
const authApiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  // Avoid Node.js proxy-from-env URL parsing path (DEP0169 on Node 24+)
  proxy: false,
})

authApiClient.interceptors.request.use(async (config) => {
  const headers = AxiosHeaders.from(config.headers ?? {})

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json")
  }
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const requestUrl = new URL(config.url ?? "", config.baseURL ?? API_BASE_URL)
  const serviceAuthorization = await getCloudRunServiceAuthorization(requestUrl)
  if (serviceAuthorization && !headers.has("X-Serverless-Authorization")) {
    headers.set("X-Serverless-Authorization", serviceAuthorization)
  }

  config.headers = headers
  return config
})

let hasLoggedRecoverableJwtWarning = false
let hasLoggedTokenExpiryWarning = false

function formatAxiosError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    if (error instanceof Error) {
      return error.message
    }
    return "Unknown error"
  }

  const status = error.response?.status ?? "unknown"
  const responseData = error.response?.data

  if (typeof responseData === "string" && responseData.trim().length > 0) {
    return `status=${status} ${responseData}`
  }

  if (responseData && typeof responseData === "object") {
    const responseObject = responseData as Record<string, unknown>
    if (Object.keys(responseObject).length > 0) {
      const detail = responseObject.detail
      if (typeof detail === "string" && detail.trim().length > 0) {
        return `status=${status} ${detail}`
      }
      return `status=${status} ${JSON.stringify(responseObject)}`
    }
  }

  const requestUrl = error.config?.url
  return `status=${status} ${error.message}${requestUrl ? ` (${requestUrl})` : ""}`
}

function decodeJwtClaimValue(
  accessToken: string,
  claim: "exp",
): number | null {
  try {
    const parts = accessToken.split(".")
    if (parts.length !== 3) {
      return null
    }

    const base64Url = parts[1]
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/")
    const padded = `${base64}${"=".repeat((4 - (base64.length % 4)) % 4)}`
    const payloadJson = Buffer.from(padded, "base64").toString("utf8")
    const payload = JSON.parse(payloadJson) as Record<string, unknown>

    const rawExp = payload[claim]
    if (typeof rawExp === "number" && Number.isFinite(rawExp)) {
      return claim === "exp" ? rawExp * 1000 : null
    }
    if (typeof rawExp === "string") {
      const parsedExp = Number(rawExp)
      return Number.isFinite(parsedExp) ? parsedExp * 1000 : null
    }
  } catch {
    return null
  }
  return null
}

function resolveExpiresAt(
  value: unknown,
  accessToken: string | undefined,
): number {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return value
  }
  if (typeof value === "string") {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed
    }
  }

  const expiryFromToken = accessToken
    ? decodeJwtClaimValue(accessToken, "exp")
    : null
  if (expiryFromToken && expiryFromToken > 0) {
    return expiryFromToken
  }

  return 0
}

function toSafeExpiresAt(
  tokenExpiresIn: number | string | undefined,
  accessToken: string,
): number {
  const parsed = typeof tokenExpiresIn === "string"
    ? Number(tokenExpiresIn)
    : tokenExpiresIn
  if (typeof parsed === "number" && Number.isFinite(parsed) && parsed > 0) {
    return Date.now() + parsed * 1000
  }

  const expiryFromJwt = decodeJwtClaimValue(accessToken, "exp")
  return expiryFromJwt ?? 0
}

function toErrorMessage(value: unknown): string {
  if (typeof value === "string") {
    return value
  }
  if (value instanceof Error) {
    return value.message
  }
  if (typeof value === "object" && value !== null) {
    const message = (value as Record<string, unknown>).message
    if (typeof message === "string") {
      return message
    }
  }
  return ""
}

function toErrorName(value: unknown): string {
  if (value instanceof Error) {
    return value.name
  }
  if (typeof value === "object" && value !== null) {
    const name = (value as Record<string, unknown>).name
    if (typeof name === "string") {
      return name
    }
  }
  return ""
}

function includesDecryptFailure(value: unknown): boolean {
  const message = toErrorMessage(value).toLowerCase()
  const name = toErrorName(value).toLowerCase()
  return (
    message.includes("decryption operation failed") ||
    name.includes("jwedecryptionfailed")
  )
}

export function isRecoverableSessionDecryptionError(value: unknown): boolean {
  if (includesDecryptFailure(value)) {
    return true
  }
  if (typeof value !== "object" || value === null) {
    return false
  }
  const record = value as Record<string, unknown>
  return (
    includesDecryptFailure(record.error) ||
    includesDecryptFailure(record.cause)
  )
}

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null
        }

        try {
          // Call FastAPI login endpoint
          const response = await authApiClient.post<BackendLoginResponse>("/auth/login", {
            email: credentials.email,
            password: credentials.password,
          })

          const { user, access_token, refresh_token, expires_in } = response.data

          // Validate token format (JWT should have 3 parts)
          if (access_token && typeof access_token === 'string') {
            const tokenParts = access_token.split('.')
            if (tokenParts.length !== 3) {
              console.error('[authorize] Invalid access_token format from backend', {
                tokenLength: access_token.length,
                partsCount: tokenParts.length,
                tokenPreview: access_token.substring(0, 50),
              })
              throw new Error('Invalid token format received from backend')
            }

            // Debug logging in development
            if (process.env.NODE_ENV === 'development') {
              console.debug('[authorize] Token received from backend', {
                tokenLength: access_token.length,
                tokenPreview: `${access_token.substring(0, 20)}...${access_token.substring(access_token.length - 20)}`,
                partsCount: tokenParts.length,
              })
            }
          } else {
            console.error('[authorize] Missing or invalid access_token in response', {
              hasAccessToken: !!access_token,
              accessTokenType: typeof access_token,
              responseKeys: Object.keys(response.data),
            })
            throw new Error('Missing access_token in login response')
          }

          // Return user object with tokens
          const authenticatedUser: AuthenticatedUser = {
            id: user.id,
            email: user.email,
            username: user.username,
            full_name: user.full_name,
            role: user.role,
            email_verified: user.email_verified,
            access_token,
            refresh_token,
            expires_at: toSafeExpiresAt(expires_in, access_token), // Convert to milliseconds
          }

          return authenticatedUser
        } catch (error) {
          console.error("Authentication error:", error)
          // Log more details for debugging
          if (axios.isAxiosError(error)) {
            if (error.response) {
              console.error("Backend response status:", error.response.status)
              console.error("Backend response data:", error.response.data)
            } else if (error.request) {
              console.error("No response received from backend:", error.request)
            } else if (error.message) {
              console.error("Error setting up request:", error.message)
            }
          } else if (error instanceof Error) {
            console.error("Unexpected authentication error:", error.message)
          }
          return null
        }
      }
    })
  ],
  session: {
    strategy: "jwt",
    maxAge: 24 * 60 * 60, // 24 hours
  },
  jwt: {
    maxAge: 24 * 60 * 60, // 24 hours
  },
  callbacks: {
    async jwt({ token, user, account }) {
      // Initial sign in
      if (user && account) {
        const customUser = user as AuthenticatedUser

        // Validate token format before storing
        if (customUser.access_token) {
          const tokenParts = customUser.access_token.split('.')
          if (tokenParts.length !== 3) {
            console.error('[jwt callback] Invalid access_token format', {
              tokenLength: customUser.access_token?.length || 0,
              partsCount: tokenParts.length,
              tokenPreview: customUser.access_token?.substring(0, 50) || 'null',
            })
            throw new Error('Invalid token format in JWT callback')
          }

          // Debug logging in development
          if (process.env.NODE_ENV === 'development') {
            console.debug('[jwt callback] Storing token', {
              tokenLength: customUser.access_token.length,
              tokenPreview: `${customUser.access_token.substring(0, 20)}...${customUser.access_token.substring(customUser.access_token.length - 20)}`,
              partsCount: tokenParts.length,
            })
          }
        }

        return {
          access_token: customUser.access_token,
          refresh_token: customUser.refresh_token,
          expires_at: resolveExpiresAt(customUser.expires_at, customUser.access_token),
          refresh_failed: false,
          user: {
            id: customUser.id,
            email: customUser.email!,
            username: customUser.username,
            full_name: customUser.full_name,
            role: customUser.role,
            email_verified: customUser.email_verified,
          }
        }
      }

      if (token.refresh_failed) {
        return token
      }

      // Return previous token if the access token has not expired yet
      const expiresAt = resolveExpiresAt(token.expires_at, token.access_token)
      const normalizedToken = {
        ...token,
        expires_at: expiresAt,
      }

      if (expiresAt && Date.now() < expiresAt) {
        // Ensure access_token exists before returning
        if (!token.access_token) {
          console.warn("JWT callback: Token exists but missing access_token", { token })
        }
        return normalizedToken
      }

      // If token expired or missing, return null to force re-authentication
      if (!expiresAt || Date.now() >= expiresAt) {
        if (process.env.NODE_ENV === "development" && !hasLoggedTokenExpiryWarning) {
          hasLoggedTokenExpiryWarning = true
          console.debug("[jwt callback] Token expired or missing expires_at", {
            expiresAt,
            now: Date.now(),
            hasAccessToken: !!token.access_token,
          })
        }
      }

      // Access token has expired, try to refresh it
      const refreshToken = token.refresh_token
      if (!refreshToken) {
        console.error("JWT callback: Cannot refresh token - refresh_token is missing", { token })
        return {
          ...normalizedToken,
          access_token: '',
          refresh_token: '',
          expires_at: 0,
          refresh_failed: true,
        }
      }

      try {
        const response = await authApiClient.post<{ access_token: string; refresh_token: string; expires_in: number }>("/auth/refresh", {
          refresh_token: refreshToken
        })

        const { access_token, refresh_token, expires_in } = response.data

        if (!access_token) {
          console.error("JWT callback: Token refresh succeeded but no access_token returned")
          // Return token as-is if refresh failed
          return token
        }

        return {
          ...normalizedToken,
          access_token,
          refresh_token,
          expires_at: Date.now() + expires_in * 1000,
          refresh_failed: false,
        }
      } catch (error) {
        const isExpectedRefresh401 = axios.isAxiosError(error) && error.response?.status === 401
        if (!isExpectedRefresh401) {
          console.error("Token refresh error:", formatAxiosError(error))
        }
        return {
          ...normalizedToken,
          access_token: '',
          refresh_token: '',
          expires_at: 0,
          refresh_failed: true,
        }
      }
    },
    async session({ session, token }) {
      const tokenAccessToken = token.access_token
      const tokenUser = token.user

      if (tokenUser) {
        session.user = {
          ...session.user,
          id: tokenUser.id,
          email: tokenUser.email,
          username: tokenUser.username,
          full_name: tokenUser.full_name,
          role: tokenUser.role,
          email_verified: tokenUser.email_verified,
          access_token: tokenAccessToken,
          expires_at: token.expires_at,
        }

        // Debug: Log if access_token is missing
        if (!tokenAccessToken && !token.refresh_failed) {
          console.error("Session callback: access_token is missing from token!", {
            tokenKeys: Object.keys(token || {}),
            hasUser: !!tokenUser,
            hasAccessToken: !!tokenAccessToken,
          })
        }
      } else {
        // Log warning if session is missing user data
        console.warn("Session callback: token.user is missing", {
          token,
          tokenKeys: Object.keys(token as Record<string, unknown>),
        })
      }
      return session
    },
  },
  logger: {
    error(code, metadata) {
      if (
        code === "JWT_SESSION_ERROR" &&
        (isRecoverableSessionDecryptionError(metadata) ||
          (typeof metadata === "object" &&
            metadata !== null &&
            Object.keys(metadata as Record<string, unknown>).length === 0))
      ) {
        if (process.env.NODE_ENV === "development" && !hasLoggedRecoverableJwtWarning) {
          hasLoggedRecoverableJwtWarning = true
          console.warn(
            "[next-auth][warn][JWT_SESSION_RECOVERABLE] Stale session cookie detected; continuing as signed out."
          )
        }
        return
      }

      console.error(`[next-auth][error][${code}]`, metadata)
    },
    warn(code) {
      console.warn(`[next-auth][warn][${code}]`)
    },
    debug(code, metadata) {
      if (process.env.NODE_ENV === "development") {
        console.debug(`[next-auth][debug][${code}]`, metadata)
      }
    },
  },
  pages: {
    signIn: "/auth/login",
    error: "/auth/login", // Error code passed in query string as ?error=
  },
  secret: process.env.NEXTAUTH_SECRET,
}
