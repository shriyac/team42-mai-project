"""Refuse direct pytest execution; use the credential-isolated source runner."""
import os

if os.environ.get("LAGA_TEST_ISOLATED") != "1":
    raise RuntimeError("Use node scripts/run-isolated-tests.mjs python; direct pytest is not credential-isolated")
