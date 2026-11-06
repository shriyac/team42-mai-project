---
name: Preview private-file security
description: Why Git exclusions do not protect runtime files from a development HTTP server.
---

Treat development preview file serving as an independent security boundary.
Git-ignored databases, credentials and operator bindings must also be excluded
from HTTP filesystem access.

**Why:** A workspace-root development allowlist made private runtime files
reachable via a filesystem URL even though ordinary data URLs returned the SPA.
Neither Git ignore rules nor a successful normal-route check proved isolation.

**How to apply:** Preserve private-file denial when changing preview roots,
allowlists or tooling. Verify filesystem-route variants as well as ordinary URLs
without logging file contents. A prior credential exposure requires a separate
credential/session rotation decision; blocking future reads does not undo it.

Never run the regression suite with real bootstrap secrets inherited by tests.

**Why:** A random-password bootstrap test inherited the operator password and
printed it in a failed equality assertion. Capturing normal application logs
alone does not prevent test-framework diagnostics from revealing secrets.

**How to apply:** Remove real bootstrap passwords and runtime database settings
from test-process environments; supply explicit synthetic values only in tests
that need them. Use process-local credentials without assertion value dumps
for live authentication verification. Treat a diagnostic disclosure as an
exposure requiring a new secret and a fresh or safely rotated installation.
