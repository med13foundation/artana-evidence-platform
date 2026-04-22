# Artana Front Door Website PRD

## Document Control
- Product: Artana Resource Library Front Door Website
- Status: Draft v1
- Last updated: 2026-02-27
- Owner: Platform team
- Repository: `/Users/alvaro1/Documents/med13/foundation/resource_library`

## 1. Executive Summary
Artana needs a public-facing "front door" website that explains the platform, builds trust, and routes visitors to the right next step (request access, documentation, demo, contact). This website must be deployable as an independent service and container, while remaining in the same monorepo.

Decision: keep a single monorepo, but create a separate app and container for the front door website.

## 2. Problem Statement
Current web surface (`src/web`) is the authenticated admin product. It is not optimized for:
- public messaging and positioning
- SEO and discoverability
- conversion-focused journeys for new visitors
- independent release cadence for marketing/content updates

Without a dedicated front door:
- new users land in product-oriented UX too early
- content and product concerns remain coupled
- deployments and quality gates are harder to scope by intent

## 3. Goals and Non-Goals

### 3.1 Goals
1. Launch a public website as a standalone service/container.
2. Keep implementation in this repo with strict service boundaries.
3. Support independent CI/CD and deployment from admin/backend.
4. Provide clear conversion paths: docs, demo request, contact, access.
5. Meet production quality standards for security, performance, accessibility, and SEO.

### 3.2 Non-Goals
1. Replacing the current admin UI (`src/web`).
2. Moving to multi-repo or git submodules.
3. Building a CMS in v1.
4. Adding direct database access from the front door service.

## 4. Users and Core Jobs

### 4.1 Primary audiences
1. Research leads evaluating the platform.
2. Technical evaluators (engineers, data teams).
3. Compliance/security stakeholders.
4. Existing users needing fast links to docs/admin access.

### 4.2 Jobs to be done
1. Understand what MED13 does and why it is credible.
2. Evaluate architecture/security posture quickly.
3. Find how to start (docs, contact, demo, request access).
4. Reach the correct product surface without confusion.

## 5. Scope

### 5.1 MVP scope
1. Public landing page with value proposition and architecture overview.
2. Solutions/use-cases page (biomedical first, domain-agnostic framing).
3. Security and compliance page.
4. Developer quickstart page linking to docs.
5. Contact/request access form endpoint integration.
6. Navigation links to admin login and docs.
7. Basic analytics and conversion tracking.

### 5.2 Post-MVP scope
1. Blog/changelog.
2. Customer stories/case studies.
3. Localization.
4. A/B testing framework.

## 6. Information Architecture
Required routes for v1:
1. `/` (home)
2. `/platform`
3. `/security`
4. `/developers`
5. `/contact`
6. `/request-access`
7. `/legal/privacy`
8. `/legal/terms`

Global nav:
1. Platform
2. Security
3. Developers
4. Docs (external link)
5. Admin login
6. Request access (primary CTA)

## 7. Functional Requirements

### 7.1 Content and UX
- FR-001: Home page must communicate platform value in under 10 seconds of reading.
- FR-002: Every top-level page must include a primary CTA and a secondary CTA.
- FR-003: Security page must summarize RLS, PHI encryption, and audit logging at a high level.
- FR-004: Developers page must provide quickstart links to canonical docs.
- FR-005: Contact and request-access forms must validate input and show success/error states.
- FR-006: Global footer must include legal links and support contact.

### 7.2 Integration and routing
- FR-007: "Admin login" CTA must route to current admin service URL.
- FR-008: "Docs" CTA must route to docs endpoint/location.
- FR-009: No direct front door imports from `src/web`; only shared contracts if explicitly created.

### 7.3 Analytics
- FR-010: Track page views, CTA clicks, and form submissions.
- FR-011: Capture UTM source/medium/campaign on form submissions.

## 8. Non-Functional Requirements

### 8.1 Performance
- NFR-001: Lighthouse Performance score >= 90 on desktop and mobile.
- NFR-002: LCP <= 2.5s on 75th percentile mobile.
- NFR-003: CLS <= 0.1.
- NFR-004: Serve compressed assets and cache static resources.

### 8.2 Accessibility
- NFR-005: WCAG 2.2 AA baseline compliance.
- NFR-006: Full keyboard navigation for all interactive controls.
- NFR-007: Semantic heading order and ARIA labels where required.

### 8.3 SEO
- NFR-008: Per-page metadata (title, description, canonical).
- NFR-009: OpenGraph and Twitter card metadata for core pages.
- NFR-010: XML sitemap and robots.txt.

### 8.4 Security
- NFR-011: No PHI collection in front door forms.
- NFR-012: Strict server-side input validation on form payloads.
- NFR-013: Security headers and CSP defined in Next.js config.
- NFR-014: Secrets only via environment variables/secret manager.

### 8.5 Reliability
- NFR-015: 99.9% monthly uptime target for front door service.
- NFR-016: Health endpoint and structured logs for requests and errors.

## 9. Technical Architecture

### 9.1 Monorepo strategy
Keep one repo. Add a separate app and container.

Exact location:
- `/Users/alvaro1/Documents/med13/foundation/resource_library/services/frontdoor`

### 9.2 Required folder structure
```text
services/frontdoor/
  app/
  components/
  lib/
  public/
  tests/
  package.json
  package-lock.json
  tsconfig.json
  next.config.js
  Dockerfile
  .dockerignore
  .env.example
  README.md
```

### 9.3 Service boundaries
1. `src/web` remains authenticated admin product.
2. `services/frontdoor` is public marketing/onboarding surface.
3. Backend remains in root python app (`src/`).
4. Front door communicates with backend only through HTTP APIs (if needed).

### 9.4 Shared contracts policy
If type sharing is needed, create explicit shared contracts package (later). Do not cross-import runtime code from admin app.

## 10. Container and Deployment Design

### 10.1 Container
- Build context: `services/frontdoor`
- Dockerfile path: `services/frontdoor/Dockerfile`
- Runtime port: 3000
- Cloud Run service name: `med13-frontdoor` (+ `-dev`, `-staging`)

### 10.2 Environment variables (minimum)
- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_ADMIN_URL`
- `NEXT_PUBLIC_DOCS_URL`
- `NEXT_PUBLIC_SITE_URL`
- `CONTACT_FORM_ENDPOINT` (server-only)

### 10.3 Deployment model
Separate Cloud Run service from:
1. `med13-resource-library` (API)
2. `med13-admin` (admin)

New service:
3. `med13-frontdoor`

## 11. CI/CD Requirements

### 11.1 Workflow separation
Create a dedicated workflow:
- `.github/workflows/frontdoor-deploy.yml`

### 11.2 Path filters
Front door workflow triggers only on:
- `services/frontdoor/**`
- workflow file changes

### 11.3 Required checks
1. Install deps (`npm ci` in `services/frontdoor`)
2. Lint
3. Type-check
4. Unit tests
5. Build
6. Container build
7. Trivy scan

### 11.4 Existing workflow updates
Current workflows are hardcoded to `src/web`. Add frontdoor-specific jobs, do not merge concerns into one unscoped job.

## 12. Security and Compliance
1. No PHI data collection in public forms.
2. Rate-limit and anti-spam protection for contact endpoints.
3. Content sanitization for any rich text rendering.
4. CSP and security headers aligned with existing security baseline.
5. Audit events for form submissions and backend integration calls.

## 13. Content and Messaging Requirements
1. Describe MED13 as domain-agnostic platform, biomedical-first implementation.
2. Include evidence of trust: architecture, security controls, auditability.
3. Keep technical claims consistent with implemented features.
4. Include clear handoff paths to docs and access onboarding.

## 14. Delivery Plan and Milestones

### Phase 0: Discovery and content (3-4 days)
1. Finalize sitemap, messaging, CTA copy.
2. Approve KPI definitions.

### Phase 1: App scaffold and infra (3-4 days)
1. Create `services/frontdoor`.
2. Add Dockerfile and local run targets.
3. Add standalone CI workflow.

### Phase 2: MVP build (1-2 weeks)
1. Implement v1 routes and UI.
2. Integrate analytics and forms.
3. Add SEO/accessibility/performance hardening.

### Phase 3: Launch hardening (3-4 days)
1. Lighthouse and accessibility sign-off.
2. Security review and container scan pass.
3. Staging smoke tests and production rollout.

## 15. Acceptance Criteria
1. Front door app exists at `services/frontdoor` with independent `package.json`.
2. Separate container builds from `services/frontdoor/Dockerfile`.
3. Separate Cloud Run service deploys independently of admin/backend.
4. CI for front door passes without requiring unrelated backend/admin changes.
5. All MVP routes are available and linked from nav/footer.
6. Lighthouse >= 90 (mobile + desktop) on homepage and one internal page.
7. Accessibility audit has no critical blockers.
8. Contact/request-access flow works end-to-end in staging.

## 16. Risks and Mitigations
1. Risk: duplicated frontend tooling between admin and front door.
   Mitigation: standardize Node version, lint config baseline, and CI templates.
2. Risk: unclear ownership of content updates.
   Mitigation: define CODEOWNERS for `services/frontdoor/**`.
3. Risk: accidental coupling with admin app.
   Mitigation: enforce path boundaries and separate workflows/deploy units.
4. Risk: backend deployment triggered for website-only changes.
   Mitigation: path-filtered workflows.

## 17. Open Questions
1. Should front door be publicly unauthenticated in all environments?
2. Which analytics provider is approved for compliance constraints?
3. Will forms post to backend API directly or through a managed provider?
4. Is multilingual support required in 2026 roadmap?

## 18. Implementation Checklist (Repository-Level)
1. Create `/services/frontdoor` app.
2. Add `services/frontdoor/Dockerfile` and `services/frontdoor/.dockerignore`.
3. Update root `.dockerignore` to exclude `services/frontdoor` from backend image context.
4. Add `make frontdoor-install`, `make frontdoor-dev`, `make frontdoor-build`, `make frontdoor-test`.
5. Add `.github/workflows/frontdoor-deploy.yml`.
6. Add docs links in root `README.md` and `docs/README.md`.
7. Add `CODEOWNERS` entry for `services/frontdoor/**`.
