# React Security Hardening Guide

**Last Updated:** January 2025
**Status:** Active Security Posture

This document outlines the security measures implemented in the Artana Resource Library Next.js admin interface to protect against common React vulnerabilities and attacks.

## 🚨 Critical Vulnerabilities Addressed

### CVE-2025-55182 (React2Shell) - React Server Components RCE

**Status:** ✅ **NOT AFFECTED** (Using React 18.3.1)

While we're currently on React 18.3.1 and not directly affected by this vulnerability, we maintain vigilance:

- **Current Version:** React 18.3.1 (stable, secure)
- **Future Upgrades:** When upgrading to React 19.x, ensure:
  - Upgrade to patched versions (19.0.1+, 19.1.2+, 19.2.1+)
  - Update `react-server-dom-webpack`, `react-server-dom-parcel`, `react-server-dom-turbopack` if used
  - Test Server Actions thoroughly after upgrade

**Reference:**
- [React Security Advisory](https://react.dev/blog/2025/12/03/critical-security-vulnerability-in-react-server-components)
- [Unit 42 Analysis](https://unit42.paloaltonetworks.com/cve-2025-55182-react-and-cve-2025-66478-next/)

## 🛡️ Security Measures Implemented

### 1. Dependency Security

#### Automated Security Scanning

**npm Audit Integration:**
```bash
# Run security audit (moderate+ severity)
npm run security:audit

# Fix automatically fixable issues
npm run security:audit:fix

# Strict audit (all severities)
npm run security:audit:strict

# Full security check (audit + outdated)
npm run security:check
```

**CI/CD Integration:**
- Daily automated security scans via GitHub Actions
- Blocking on critical vulnerabilities
- Artifact storage for audit results
- Automated alerts for new vulnerabilities

**Package Update Strategy:**
- Regular dependency updates (monthly reviews)
- Patch-level updates applied immediately
- Major version updates require testing and approval
- All updates verified with automated tests

### 2. XSS Prevention

#### HTML Sanitization

**DOMPurify Integration:**
We use `isomorphic-dompurify` for safe HTML sanitization when user content must be rendered.

```typescript
import { sanitizeHtml } from '@/lib/security/sanitize'

// Safe HTML rendering
const userContent = "<p>Hello <script>alert('XSS')</script></p>"
const safe = sanitizeHtml(userContent)
// Result: "<p>Hello </p>" (script removed)
```

**Usage Guidelines:**
- ✅ **DO:** Use `sanitizeHtml()` for any user-generated HTML
- ✅ **DO:** Use `stripHtml()` for plain text previews
- ❌ **DON'T:** Use `dangerouslySetInnerHTML` without sanitization
- ❌ **DON'T:** Trust any HTML from external APIs without sanitization

**Current Status:**
- ✅ No `dangerouslySetInnerHTML` usage found in codebase
- ✅ DOMPurify available for future needs
- ✅ Security utilities documented and tested

### 3. Content Security Policy (CSP)

**Current CSP Configuration:**
```javascript
// Enhanced CSP headers in next.config.js
- default-src 'self'
- frame-ancestors 'none' (prevents clickjacking)
- script-src 'self' 'unsafe-inline' 'unsafe-eval' (Next.js requirement)
- style-src 'self' 'unsafe-inline' (Next.js requirement)
- base-uri 'self' (prevents base tag injection)
- form-action 'self' (prevents form hijacking)
- upgrade-insecure-requests (forces HTTPS)
```

**CSP Notes:**
- `unsafe-inline` and `unsafe-eval` are required for Next.js HMR and some features
- In production, consider implementing nonces for stricter CSP
- CSP is enforced via Next.js headers configuration

### 4. Server Actions Security

**Current Implementation:**
- ✅ Server Actions use `"use server"` directive
- ✅ All Server Actions require authentication
- ✅ Token validation on every request
- ✅ Error handling prevents information leakage

**Best Practices:**
```typescript
// Example: Secure Server Action
"use server"

export async function secureAction(data: Input) {
  // 1. Authenticate
  const token = await getAuthToken()

  // 2. Validate input
  const validated = schema.parse(data)

  // 3. Authorize (server-side)
  await checkPermissions(token, validated)

  // 4. Execute with error handling
  try {
    return await performAction(validated)
  } catch (error) {
    // Don't leak sensitive error details
    throw new Error("Operation failed")
  }
}
```

### 5. API Key and Secret Management

**Security Rules:**
- ✅ **NEVER** hardcode API keys in frontend code
- ✅ All secrets stored in environment variables
- ✅ `NEXT_PUBLIC_*` variables are public (treat as such)
- ✅ Sensitive operations require backend API calls
- ✅ Automated scanning detects hardcoded secrets

**Environment Variables:**
```bash
# Public (safe for frontend)
NEXT_PUBLIC_API_URL=http://localhost:8080

# Private (server-side only)
NEXTAUTH_SECRET=...  # Never exposed to client
DATABASE_URL=...     # Backend only
```

### 6. Authorization Checks

**Multi-Layer Security:**
1. **Client-Side Guards:** UX improvements, not security
2. **Server-Side Validation:** Real security enforcement
3. **API-Level Authorization:** Backend validates all requests

**Implementation Pattern:**
```typescript
// Client-side (UX only)
if (user.role !== 'admin') {
  return <AccessDenied />
}

// Server-side (real security)
export default async function AdminPage() {
  const session = await getServerSession(authOptions)
  if (session?.user?.role !== 'admin') {
    redirect('/dashboard?error=AdminOnly')
  }
  // Render admin content
}
```

## 🔍 Security Scanning & Monitoring

### Automated Scans

**GitHub Actions Workflow:**
- **Schedule:** Daily at 2 AM UTC
- **Triggers:** Push to main/develop, PRs, manual dispatch
- **Checks:**
  - npm audit (moderate+ severity)
  - Outdated package detection
  - Dangerous pattern scanning
  - Hardcoded secret detection
  - eval() usage detection

**Local Scanning:**
```bash
# Run security checks locally
cd src/web
npm run security:check

# Or use Makefile
make web-lint  # Includes security patterns
```

### Manual Security Reviews

**Before Production Deployment:**
1. ✅ Review npm audit results
2. ✅ Verify no hardcoded secrets
3. ✅ Test authentication flows
4. ✅ Verify CSP headers
5. ✅ Review Server Actions for proper auth
6. ✅ Check for XSS vulnerabilities

## 📋 Security Checklist

### Pre-Deployment

- [ ] All dependencies updated and audited
- [ ] No critical/high vulnerabilities
- [ ] No hardcoded secrets in code
- [ ] CSP headers configured
- [ ] Server Actions properly authenticated
- [ ] User input sanitized (if HTML rendering)
- [ ] Authorization checks on server-side
- [ ] Error messages don't leak sensitive info

### Ongoing Maintenance

- [ ] Weekly dependency updates review
- [ ] Monthly security audit review
- [ ] Quarterly security best practices review
- [ ] Monitor security advisories
- [ ] Update security documentation

## 🚀 Quick Reference

### Security Commands

```bash
# Frontend security
cd src/web
npm run security:audit          # Check vulnerabilities
npm run security:audit:fix     # Auto-fix issues
npm run security:check          # Full security check

# Backend security (from root)
make security-audit             # Python dependencies
make lint-strict                # Code quality + security
```

### Security Utilities

```typescript
// HTML Sanitization
import { sanitizeHtml, stripHtml } from '@/lib/security/sanitize'

// URL Validation
import { isSafeUrl } from '@/lib/security/sanitize'
```

### Emergency Response

**If a vulnerability is discovered:**

1. **Assess:** Determine severity and impact
2. **Patch:** Update affected dependencies immediately
3. **Test:** Verify fix doesn't break functionality
4. **Deploy:** Push fix to production ASAP
5. **Monitor:** Watch for exploitation attempts
6. **Document:** Update this guide with lessons learned

## 📚 Additional Resources

- [React Security Best Practices](https://react.dev/learn/escape-hatches)
- [Next.js Security Headers](https://nextjs.org/docs/app/api-reference/next-config-js/headers)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [npm Security Best Practices](https://docs.npmjs.com/security-best-practices)

## 🔄 Update History

- **2025-01-XX:** Initial security hardening implementation
  - Added DOMPurify for HTML sanitization
  - Enhanced CSP headers
  - Implemented automated security scanning
  - Created security utilities library

---

**Remember:** Security is an ongoing process, not a one-time setup. Regular reviews and updates are essential.
