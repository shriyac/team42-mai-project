---
name: Documentation checksums
description: Why handoff checksum validation must account for Windows and Linux line endings.
---

Validate generated handoff checksums against both LF and CRLF representations of the same source.

**Why:** The imported documentation was generated from Windows CRLF source, while Git imported the specification with LF. Raw-byte checksums differ despite identical contract content. Do not regenerate the PDF or replace its provenance merely to accommodate a checkout's line endings.

**How to apply:** Preserve content-sensitive checksum checks, accepting only those two line-ending representations when validating the handoff.
