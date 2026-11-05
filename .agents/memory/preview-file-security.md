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
