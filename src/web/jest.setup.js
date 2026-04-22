// Optional: configure or set up a testing framework before each test.
// If you delete this file, remove `setupFilesAfterEnv` from `jest.config.js`

// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'
import { TextDecoder, TextEncoder } from 'util'

jest.mock('server-only', () => ({}))

if (!global.TextEncoder) {
  global.TextEncoder = TextEncoder
}

if (!global.TextDecoder) {
  global.TextDecoder = TextDecoder
}

if (!global.Headers) {
  global.Headers = class Headers {
    constructor(init = {}) {
      this.map = new Map(Object.entries(init))
    }

    append(name, value) {
      this.map.set(name.toLowerCase(), String(value))
    }

    get(name) {
      return this.map.get(name.toLowerCase()) ?? null
    }
  }
}

if (!global.Request) {
  global.Request = class Request {
    constructor(input, init = {}) {
      this.url = typeof input === 'string' ? input : input?.url ?? ''
      this.method = init.method ?? 'GET'
      this.headers = new global.Headers(init.headers ?? {})
    }
  }
}

if (!global.Response) {
  global.Response = class Response {
    constructor(body = null, init = {}) {
      this.body = body
      this.status = init.status ?? 200
      this.headers = new global.Headers(init.headers ?? {})
      this.ok = this.status >= 200 && this.status < 300
    }
  }
}

if (!global.fetch) {
  global.fetch = jest.fn(async () => new global.Response(null))
}

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
      refresh: jest.fn(),
      pathname: '/',
      query: {},
    }
  },
  useSearchParams() {
    return new URLSearchParams()
  },
  usePathname() {
    return '/'
  },
  redirect: jest.fn((url) => {
    const error = new Error('NEXT_REDIRECT')
    error.digest = `NEXT_REDIRECT;${url}`
    throw error
  }),
}))

// Mock next-themes
jest.mock('next-themes', () => ({
  ThemeProvider: ({ children, ...props }) => <div {...props}>{children}</div>,
  useTheme: () => ({
    theme: 'light',
    setTheme: jest.fn(),
    themes: ['light', 'dark', 'system'],
  }),
}))

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  observe() {
    return null
  }
  disconnect() {
    return null
  }
  unobserve() {
    return null
  }
}
