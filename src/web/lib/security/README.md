# Security Utilities

This directory contains security utilities for the Artana Resource Library Next.js admin interface.

## Modules

### `sanitize.ts`

HTML sanitization utilities using DOMPurify to prevent XSS attacks.

**Exports:**
- `sanitizeHtml(dirty: string, config?: DOMPurify.Config): string` - Sanitize HTML content
- `sanitizeHtmlWithSecureLinks(dirty: string): string` - Sanitize HTML with secure link attributes
- `stripHtml(html: string): string` - Remove all HTML tags, return plain text
- `isSafeUrl(url: string): boolean` - Validate URL safety for href attributes

**Usage:**
```typescript
import { sanitizeHtml, stripHtml, isSafeUrl } from '@/lib/security/sanitize'

// Sanitize user-generated HTML
const safe = sanitizeHtml(userContent)

// Get plain text preview
const preview = stripHtml(htmlContent)

// Validate URL before using in href
if (isSafeUrl(userUrl)) {
  return <a href={userUrl}>Link</a>
}
```

## Security Best Practices

1. **Always sanitize user-generated HTML** before rendering
2. **Never use `dangerouslySetInnerHTML`** without sanitization
3. **Validate URLs** before using in links
4. **Use server-side validation** for all user inputs
5. **Never trust client-side security checks** - always validate on the server

## Related Documentation

- [React Security Hardening Guide](../../../../docs/security/react-security-hardening.md)
- [DOMPurify Documentation](https://github.com/cure53/DOMPurify)
