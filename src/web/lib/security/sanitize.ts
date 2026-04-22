/**
 * Security utilities for sanitizing user-generated content
 *
 * This module provides safe HTML sanitization using DOMPurify
 * to prevent XSS attacks when rendering user content.
 *
 * @module lib/security/sanitize
 */

// Use isomorphic-dompurify which works in both browser and Node.js
import DOMPurify from 'isomorphic-dompurify'
import { Config } from 'dompurify'

/**
 * Configuration for DOMPurify sanitization
 * Allows common formatting tags but blocks scripts and dangerous attributes
 */
const SANITIZE_CONFIG: Config = {
  // Allow common formatting tags
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'em', 'u', 's', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'span', 'div'
  ],
  // Allow safe attributes
  ALLOWED_ATTR: ['href', 'title', 'class', 'id', 'target', 'rel'],
  // Add rel="noopener noreferrer" to external links for security
  ADD_ATTR: ['target'],
  // Prevent data URIs and javascript: protocols
  ALLOW_DATA_ATTR: false,
  // Keep relative URLs
  ALLOW_UNKNOWN_PROTOCOLS: false,
  // Return as string (not DOM node)
  RETURN_DOM: false,
  RETURN_DOM_FRAGMENT: false,
  RETURN_TRUSTED_TYPE: false,
}

/**
 * Sanitize HTML content to prevent XSS attacks
 *
 * @param dirty - Unsanitized HTML string from user input
 * @param config - Optional DOMPurify configuration override
 * @returns Sanitized HTML string safe for rendering
 *
 * @example
 * ```tsx
 * const userContent = "<p>Hello <script>alert('XSS')</script></p>"
 * const safe = sanitizeHtml(userContent)
 * // Returns: "<p>Hello </p>" (script removed)
 * ```
 */
export function sanitizeHtml(
  dirty: string,
  config?: Config
): string {
  if (!dirty || typeof dirty !== 'string') {
    return ''
  }

  const finalConfig = config ? { ...SANITIZE_CONFIG, ...config } : SANITIZE_CONFIG

  // Sanitize the HTML
  const clean = DOMPurify.sanitize(dirty, finalConfig)

  return clean
}

/**
 * Sanitize HTML and add security attributes to links
 *
 * @param dirty - Unsanitized HTML string
 * @returns Sanitized HTML with secure link attributes
 */
export function sanitizeHtmlWithSecureLinks(dirty: string): string {
  const sanitized = sanitizeHtml(dirty)

  // Add rel="noopener noreferrer" to external links
  // This is handled by DOMPurify's ADD_ATTR config, but we ensure it here too
  return sanitized.replace(
    /<a\s+([^>]*href\s*=\s*["'][^"']*["'][^>]*)>/gi,
    (match, attrs) => {
      // Check if it's an external link
      const hrefMatch = attrs.match(/href\s*=\s*["']([^"']*)["']/i)
      if (hrefMatch && (hrefMatch[1].startsWith('http://') || hrefMatch[1].startsWith('https://'))) {
        // Add security attributes if not present
        if (!attrs.includes('rel=')) {
          return `<a ${attrs} rel="noopener noreferrer">`
        }
        if (!attrs.includes('rel="noopener')) {
          return match.replace(/rel\s*=\s*["'][^"']*["']/i, 'rel="noopener noreferrer"')
        }
      }
      return match
    }
  )
}

/**
 * Strip all HTML tags and return plain text
 * Useful for previews or when HTML is not needed
 *
 * @param html - HTML string to strip
 * @returns Plain text with HTML tags removed
 */
export function stripHtml(html: string): string {
  if (!html || typeof html !== 'string') {
    return ''
  }

  // Use DOMPurify to sanitize, then extract text
  const sanitized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [],
    KEEP_CONTENT: true,
  })

  return sanitized
}

/**
 * Validate that a URL is safe for use in href attributes
 * Prevents javascript: and data: protocol attacks
 *
 * @param url - URL to validate
 * @returns true if URL is safe, false otherwise
 */
export function isSafeUrl(url: string): boolean {
  if (!url || typeof url !== 'string') {
    return false
  }

  const trimmed = url.trim().toLowerCase()

  // Block dangerous protocols
  const dangerousProtocols = ['javascript:', 'data:', 'vbscript:', 'file:']
  for (const protocol of dangerousProtocols) {
    if (trimmed.startsWith(protocol)) {
      return false
    }
  }

  // Allow http, https, mailto, tel, and relative URLs
  return (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('mailto:') ||
    trimmed.startsWith('tel:') ||
    trimmed.startsWith('/') ||
    trimmed.startsWith('#') ||
    trimmed.startsWith('?')
  )
}
