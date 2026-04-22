import {
  getDefaultPostLoginDestination,
  normalizePostLoginCallbackPath,
  resolvePostLoginDestination,
} from '@/lib/post-login-destination'
import { UserRole } from '@/types/auth'

const CURRENT_ORIGIN = 'https://artana.example.com'

describe('post-login destination helpers', () => {
  describe('getDefaultPostLoginDestination', () => {
    it('defaults admins to dashboard', () => {
      expect(getDefaultPostLoginDestination(UserRole.ADMIN)).toBe('/dashboard')
    })

    it('defaults non-admin users to spaces', () => {
      expect(getDefaultPostLoginDestination(UserRole.VIEWER)).toBe('/spaces')
      expect(getDefaultPostLoginDestination(UserRole.RESEARCHER)).toBe('/spaces')
    })
  })

  describe('normalizePostLoginCallbackPath', () => {
    it('normalizes same-origin absolute URLs and preserves query strings and hashes', () => {
      expect(
        normalizePostLoginCallbackPath(
          'https://artana.example.com/spaces/space-1?tab=members#invite',
          CURRENT_ORIGIN,
        ),
      ).toBe('/spaces/space-1?tab=members#invite')
    })

    it('accepts app-relative callback paths', () => {
      expect(
        normalizePostLoginCallbackPath('/spaces/space-1?tab=overview', CURRENT_ORIGIN),
      ).toBe('/spaces/space-1?tab=overview')
    })

    it('rejects external absolute URLs', () => {
      expect(
        normalizePostLoginCallbackPath(
          'https://evil.example/phishing?next=/spaces',
          CURRENT_ORIGIN,
        ),
      ).toBeNull()
    })

    it('rejects protocol-relative and javascript URLs', () => {
      expect(
        normalizePostLoginCallbackPath('//evil.example/phishing', CURRENT_ORIGIN),
      ).toBeNull()
      expect(
        normalizePostLoginCallbackPath('javascript:alert(1)', CURRENT_ORIGIN),
      ).toBeNull()
    })
  })

  describe('resolvePostLoginDestination', () => {
    it('preserves non-admin callback URLs for allowed pages', () => {
      expect(
        resolvePostLoginDestination('/spaces/space-1', UserRole.VIEWER, CURRENT_ORIGIN),
      ).toBe('/spaces/space-1')
    })

    it('reroutes non-admin users away from admin-only paths', () => {
      expect(
        resolvePostLoginDestination('/dashboard', UserRole.VIEWER, CURRENT_ORIGIN),
      ).toBe('/spaces')
      expect(
        resolvePostLoginDestination(
          'https://artana.example.com/system-settings?tab=users',
          UserRole.CURATOR,
          CURRENT_ORIGIN,
        ),
      ).toBe('/spaces')
      expect(
        resolvePostLoginDestination('/admin/dictionary', UserRole.RESEARCHER, CURRENT_ORIGIN),
      ).toBe('/spaces')
    })

    it('keeps admin-only callback URLs for admins', () => {
      expect(
        resolvePostLoginDestination('/dashboard', UserRole.ADMIN, CURRENT_ORIGIN),
      ).toBe('/dashboard')
      expect(
        resolvePostLoginDestination('/admin/dictionary', UserRole.ADMIN, CURRENT_ORIGIN),
      ).toBe('/admin/dictionary')
    })

    it('falls back to role defaults for unsafe callback URLs', () => {
      expect(
        resolvePostLoginDestination(
          'https://evil.example/phishing',
          UserRole.ADMIN,
          CURRENT_ORIGIN,
        ),
      ).toBe('/dashboard')
      expect(
        resolvePostLoginDestination('javascript:alert(1)', UserRole.VIEWER, CURRENT_ORIGIN),
      ).toBe('/spaces')
    })
  })
})
