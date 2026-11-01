---
name: Local Python installation
description: Limitation of the package helper when installing this project's own extras.
---

The package helper interprets `.[api,test]` as a dependency to add via `uv add`, which rejects it as a self-dependency.

**Why:** Installing a project's own optional extras is not the same operation as adding a third-party dependency. The helper failed before installing anything.

**How to apply:** For this operation, use pip with the project-local package target documented in `replit.md`. Do not rename the project, add it as its own dependency, or override the system Python protection.
