# Synthetic lease examination record

Review date: November 1, 2026. Corpus version: 1.1.0. Scope: every file in this directory, the source fixture JS, generation/printing/packaging scripts, lease tests, and corpus references in repository Markdown. This is a consistency examination of fictional unsigned test evidence. Attorney approval and enforceability review remain outstanding; `legalReviewStatus` intentionally remains `not_performed`.

## Loop 1: source and scenario consistency

All ten packets map to the existing tenant, lease, property and document IDs. Review covers rent/deposit cents, dates, inclusive 12-month terms, household/adult/child totals, income arithmetic, approved pets, contact tokens, unit-specific annexures and page references. Corrected the stray question mark in all household labels.

Supplied fictional assumptions, rather than facts about a real tenancy:

- First and final partial months use actual calendar days with inclusive occupancy and cent rounding. Isabella's first rent is $1,290.32 and final rent is $1,209.68. Initial rent/deposit and approved ordinary-pet fees are due at commencement. No receipt or balance is asserted.
- Regular rent is due on the first. The initial mid-month installment is an express exception. Late fees apply only once an installment is five calendar days late, once per installment, without compounding or making later rent delinquent through fee allocation.
- Monthly pet rent and shared laundry charges are $0. The $250 ordinary-pet fee is nonrefundable; households without an approved pet owe $0. Assistance animals are outside the ordinary-pet fee scenario.
- Payment destination is the landlord's nonfunctional test token; tenant account tokens identify funding accounts only. No live transfer or debit authorization is created.
- Notice receipt deadline is the inclusive end date minus 60 calendar days, using the resident portal. Fixed terms expire on the stated dates; extension requires a new agreement. Statutory termination and holding over remain review questions.

External utility tariffs, live balances, actual inspection findings and signed approvals cannot be established from synthetic data. Missing external facts are not replaced with fabricated factual assertions.

## Loop 2: cross-format and rendered output

Regenerate JSON, Markdown and HTML from the corrected JS source, then regenerate every PDF. Independently extract text from all 120 PDF pages and compare each paragraph against HTML and Markdown. Check tenant identity, manifest hashes, page counts, print overflow and citation locations. `scripts/audit-synthetic-leases.py` performs the independent text and arithmetic audit; existing Node lease tests compare against frontend fixtures.

## Loop 3: final integrity and handoff

Repeat the independent audit and full frontend suite after final corrections. Verify deterministic text generation, package inventory and ZIP integrity, and review the final diff for unrelated changes. The manifest identifies all ten packets; this file and the README describe assumptions without changing legal-review status. No numerical legal-accuracy probability is assigned.

## Recorded results

All three loops completed on November 1, 2026:

- All 10 PDF packets regenerated: 12 searchable pages each, with no detected print overflow.
- Independent extraction passed for every paragraph on all 120 pages against HTML and Markdown; JSON arithmetic, identities, hashes and all 43 corpus files passed.
- Deterministic regeneration reproduced every JSON, Markdown and HTML artifact, and the manifest matched after excluding printer metadata.
- Full frontend suite: 36 tests passed, zero failures, including fixture/citation checks, PDF identity and API handoff checks.
- Final diff whitespace check passed. Corpus ZIP contains 43 files including this record and all 10 PDFs; ZIP integrity passed.

These are observed test results, not an estimated 99.99% legal-accuracy score. The attorney questions below remain open.

## Questions for the examining attorney

| Topic | Relevant packet locations | Examination required |
| --- | --- | --- |
| Landlord capacity and notices | 1, 7.2, 12.2 | Confirm the legal lessor/entity, representative authority, service address, notice delivery/receipt and electronic-notice consent. All present identities are fictional. |
| Security deposit | 4.1-4.5 | Determine actual trust institution or bond, required custody notice, permissible deductions and return/accounting obligations. A fictional tenant funding account is not a deposit trust account. |
| Fees and proration | 3.1-3.6 | Review grace counting, partial-month treatment, subsidized-tenancy exceptions, fee limits and allocation. No payment ledger is supplied. |
| Animals and accommodations | 8.1-8.4 | Review reasonableness/refundability and accommodation obligations; ordinary-pet rules must not decide assistance-animal requests. |
| Entry, repairs and condition | 4.4, 6.4, 7 | Establish lawful access procedures, nonwaivable maintenance duties and an actual inspection record. Synthetic baseline condition is not proof. |
| Expiry, notice and remedies | 12 | Review the 60-day clause, statutory early termination, holdover, service requirements, default and lawful remedies. |
| Occupants and property restrictions | 2, 6, annexures | Confirm occupant rights, local requirements and smoking/amenity restrictions. Age/income fields are parser examples, not screening rules. |

Primary sources consulted November 1, 2026: [NC G.S. 42-46](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_42/GS_42-46.html) for late fees and [NC Tenant Security Deposit Act, Article 6](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByArticle/Chapter_42/Article_6.html) for deposit custody, accounting and ordinary-pet fees. These references support an examination checklist; they do not certify the packets or cover every applicable law.

## Reproducible checks

```powershell
node scripts/build-synthetic-leases.mjs
node scripts/print-synthetic-leases.mjs
npm.cmd test
python scripts/audit-synthetic-leases.py
python scripts/package-synthetic-leases.py
```

The independent PDF auditor requires `pypdf`; install it in a development environment with `python -m pip install pypdf`. The PDF printer requires the local debugging browser described in README.md. Hashes prove artifact identity, not legal correctness. Blank signature/date lines remain intentional.
