# Python Dependency Vulnerabilities

**Last Updated:** January 26, 2026

This register tracks Python dependency advisories detected by pip-audit and
records how we mitigate or resolve them.

## Resolved

### jaraco.context (CVE-2026-23949)
- **Status:** Resolved
- **Action:** Require `jaraco.context>=6.1.0` in development dependencies.
- **Notes:** This upgrade removes the vulnerable version flagged by pip-audit.

### nltk (GHSA-rf74-v2fm-23pw, CVE-2026-33230, CVE-2026-33231)
- **Status:** Resolved
- **Action:** Remove the optional `safety` development dependency that
  transitively installed `nltk`.
- **Notes:** The application codebase does not import `nltk`; the advisories were
  introduced only through the optional Safety CLI dependency. Dependency
  scanning now relies on `pip-audit` and `bandit` by default, and `make
  security-audit` skips the Safety scan unless the CLI is explicitly installed.

## Open (Upstream Fix Pending)

### protobuf (CVE-2026-0994)
- **Status:** Open (no fixed version listed in pip-audit output)
- **Impact:** Denial-of-service risk when parsing deeply nested
  `google.protobuf.Any` via `google.protobuf.json_format.ParseDict()`.
- **Current Version:** `protobuf 6.33.2` (minimum pinned in `pyproject.toml`)
- **Current Usage:** No direct usage of `google.protobuf` APIs in the codebase
  (checked via repository search).
- **Mitigation:** Avoid parsing untrusted protobuf `Any` payloads via
  `ParseDict()`; monitor upstream release notes for a patched protobuf version.
- **Next Step:** Bump protobuf once a fixed version is published and re-run
  `make security-audit`.
