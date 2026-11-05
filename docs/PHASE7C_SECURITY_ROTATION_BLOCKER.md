# Phase 7C — stopped at unsupported credential rotation

## Outcome

Credential rotation was **not performed**. No database, credential file,
session, Secret, or activation setting was changed. No commit or push was
performed, and local `main` was not changed.

The request explicitly requires stopping if safe rotation is unsupported.
The current repository has no tested administrative rotation operation that
coordinates existing user password hashes, session revocation, and the bootstrap
recovery document. Consequently, the later Phase 7C validation and publishing
steps were not executed.

## Reviewed code and reason for stopping

- `BackendAPI.provision_user()` inserts a new user; it does not update an
  existing password.
- The `laga-create-user` CLI calls that insertion method. It is not a
  password-reset command.
- `BackendAPI.post_auth_logout()` revokes only the supplied session.
- `bootstrap_database()` preserves initialized accounts. On subsequent starts,
  it verifies the bootstrap recovery password against the account hash.
- Changing `LAGA_BOOTSTRAP_PASSWORD` alone does not rotate existing accounts.
- Updating only SQLite would leave the recovery document inconsistent and can
  prevent startup. Updating only the document would leave old passwords valid.
- A SQLite transaction and a JSON file replacement are not a single atomic
  transaction; an offline procedure needs explicit recovery if interrupted.

`vite.config.js` and `frontend/tests/previewSecurity.test.js` were reviewed.
They preserve default Vite protections and add private runtime-file denials.
The current test covers direct filesystem routes and allowed UI/fixture
modules, but it does not establish the entire requested encoded/traversal and
production-serving matrix. Those additional checks were **not** represented as
passed in this phase.

At review, the working tree was clean on `integration/laga-mvp`. The platform
had already checkpointed the Phase 7B fix locally as
`bc4ef7b` (“Implement preview file security features and update documentation”).
The GitHub integration branch still pointed to
`f04edc2c2a214d6534721d3e7e965e62e5ba10b0`. A local checkpoint does not mean
the fix has been pushed.

## Required manual maintenance procedure

The following is an offline maintainer procedure, **not an existing supported
command and not an instruction to delete/re-bootstrap the database**. It needs
review and a rehearsal on an isolated copy before use on the demo installation.
Do not run individual database statements while the application is serving.

1. **Set the new secret securely.**
   Generate a new random password with a password manager, preferably at least
   32 random bytes encoded for text entry. Store it as
   `LAGA_BOOTSTRAP_PASSWORD` in Replit Secrets for the environment being
   maintained. The bootstrap constraints are at least 24 characters and at most
   1024 UTF-8 bytes. Never place it in a command argument, source file,
   `VITE_*` setting, report, or terminal output. Preview and a published
   installation must be maintained separately.

2. **Establish checks before downtime.**
   Retain one existing authenticated test session in a private test process
   solely to verify revocation afterward. Record nonsecret row counts and
   checksums of synthetic user profiles, organizations, lease/tenant mappings,
   documents, properties, policies, and requests. Do not print passwords,
   password hashes, session tokens, CSRF tokens, or tenant record contents.

3. **Stop the existing application workflow.**
   Ensure both Python and Vite have stopped before touching authentication
   storage. Prevent another process from restarting bootstrap during maintenance.
   Do not publish or share the preview while maintenance is in progress.

4. **Identify and validate this installation.**
   Use the configured database path and the existing `fictional-local-v1`
   bootstrap marker to locate its recovery file; do not assume a relocated
   installation uses a hard-coded path. Verify the recovery document is
   synthetic, belongs to this database, and its account IDs/emails match the
   reviewed fictional bootstrap fixture and SQLite. Abort on unknown accounts
   or ambiguous ownership. Do not reset non-demo accounts.

5. **Prepare private recovery and the replacement file.**
   With the app stopped, use SQLite's backup facility to create a consistent
   recovery copy and retain the old recovery document in a private denied
   location with restrictive permissions. Never stage these files. Prepare an
   adjacent temporary recovery JSON with mode `0600`, preserving all metadata
   and accounts and replacing only its password with the new Secret read by
   the maintenance process. Flush it before replacing the live file.

6. **Rotate only reviewed demo account authentication fields.**
   In the offline maintenance process, open SQLite and begin an immediate
   transaction. For each validated bootstrap account ID, generate a fresh
   cryptographic salt using the current backend's salt format and compute the
   new hash with `BackendAPI._hash_password(new_password, salt)`. Use
   parameterized updates to **only** `users.salt` and `users.password_hash`,
   matching the validated ID and email, and require exactly one affected row.
   Do not change user IDs, profiles, organization IDs, or synthetic records.

7. **Invalidate sessions and coordinate completion.**
   Delete all rows from `sessions` for this demo installation so existing
   browser sessions cannot survive. Do not delete/recreate `users`, leases,
   or other application tables. Replace the recovery JSON atomically with
   the prepared file and commit the database transaction while the app
   remains stopped. If any stage fails, roll back the database and restore
   the matching recovery document. If interrupted around commit, keep the
   app stopped and restore the matched database/document recovery pair;
   never guess which side completed. SQLite WAL/journal state must be
   handled through SQLite-aware recovery, not arbitrary file copying.

8. **Verify before reopening.**
   Confirm every reviewed demo account hash matches the new Secret, all
   sessions are absent, and the protected synthetic records/counts/checksums
   are unchanged. Restart the original workflow and confirm bootstrap accepts
   the updated recovery document without changing account identities.

9. **Verify through the actual HTTPS UI and API.**
   Confirm the retained old session is unauthenticated, the old password no
   longer authenticates, Maya's new login works, workspace/`lease-1` access
   works, another tenant's lease remains hidden, and logout invalidates the
   new session. Keep credentials/tokens inside the test process.

10. **Complete the security and regression gate.**
    Test ordinary, filesystem, static, traversal and encoded URL variants
    for the database, recovery JSON, environment files and private bindings.
    Check the built production server separately, using isolated fixtures
    and no live deployment unless authorized. Require 403/404 for private
    file paths; do not treat an unrelated HTML response as a full denial
    guarantee. Verify intended public assets still load. Run the full Python
    suite, frontend tests and build. Keep the app unavailable for external
    sharing if any gate fails.

11. **Retire compromised recovery material and preserve reviewed code.**
    After successful checks and the maintainer's recovery decision, retire
    old credential-bearing backup copies according to the environment's
    storage policy. File deletion is not a guarantee of physical erasure.
    Review the complete outgoing diff/history for private files, then commit
    and push only the approved security code/docs to `integration/laga-mvp`.
    Do not push local `main` or enable Pinecone.

## Current report

- Rotation: **blocked / not executed**.
- Session invalidation and new-login verification: **not executed**.
- New full regression/security matrix: **not run because of the stop gate**.
- No new commit SHA or pushed changes.
- The existing preview fix remains local; previous Phase 7B results are in
  `PHASE7B_DEMO_READINESS.md`, not fresh Phase 7C verification.
- External sharing remains blocked on credential/session rotation and the
  complete validation gate. Published deployment checks and live Pinecone
  prerequisites remain separate, unresolved work.
