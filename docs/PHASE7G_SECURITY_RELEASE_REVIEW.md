# Phase 7G — reviewed security preservation

## Scope and branch

The current branch is `integration/laga-mvp`. The six existing local security
commits since the remote branch were reviewed without rewriting or squashing
history. They preserve the Phase 7B–7F route guard, isolated tests, corrected
launcher fixtures, non-secret development configuration and incident/
verification documentation.

The outgoing implementation does not change the agent, calculator, backend
authentication, SQLite implementation, frontend application or RAG algorithms.
The `.replit` change only selects the fresh fictional database path in the
development environment; it contains no database contents or password.

This audit record is the only new staged change for the release commit.

## Fresh validation

Commands:

```sh
node scripts/run-isolated-tests.mjs all
node scripts/run-isolated-tests.mjs security
```

Results:

- API-mode frontend production build: passed.
- Full Python suite: **257 passed; 57 subtests passed**.
- Frontend suite: **46 passed; zero failures**.
- Focused isolation/private-route checks: **4 passed; zero failures**.
- One existing Starlette/AnyIO deprecation warning.
- Whitespace checks on outgoing changes: passed.

Focused tests overlap the frontend suite and are not four additional unique
tests. The isolated runner excludes real credentials/runtime inputs; no live
Pinecone calls, database re-ingestion or published deployment were needed.
No application code changed after validation.

## Credential and file review

Review covered all six outgoing commit trees and 26 unique outgoing blob
versions, not just the final working tree. Exact known credential checks
included inherited credentials and all three local installation bootstrap
passwords, plus high-confidence private-key/provider-token patterns.
No values were printed; checks reported zero findings.

The outgoing trees contain none of:

- actual `.env` files or runtime dotenv variants;
- Replit Secrets or bootstrap credential recovery files;
- generated SQLite databases or old recovery copies;
- actual private bindings, document manifests or ingestion snapshots;
- logs containing exposed credentials or temporary test output.

Existing placeholder `.env.example` files and the two previously approved public
RAG PDF fixtures are unchanged; they are not private runtime data.

The final staged audit document and commit metadata are checked again before
push. This review is not a claim that an automated scan can prove the absence
of every possible unknown secret.

## Push boundary

Only `refs/heads/integration/laga-mvp` is authorized for pushing to the matching
GitHub branch, with automatic tag following disabled. Local `main`, remote
`main`, teammate feature branches and tags must not be changed. No force push
or merge is authorized.

This file records the pre-push verification. The completion message reports the
actual final commit SHA and remote verification result.

## Remaining limits

The prior real preview/browser checks are recorded in
`docs/PHASE7F_SECURITY_VERIFICATION.md`; they were not repeated by this Git-only
preservation step. Preview continues to use the fresh fictional installation.
Retired installations must remain offline.

Live retrieval remains disabled. Authoritative approved bindings, the actual
ingestion snapshot and required provider credentials are still prerequisites;
unit tests do not authorize activation. The assistant safely reports
`RAG_UNAVAILABLE`.

Local production-serving verification is not an external deployment or a
durable/shared production database solution. No publishing, deployment,
Pinecone activation or index writes are part of this release preservation.
