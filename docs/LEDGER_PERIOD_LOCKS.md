# Ledger period posting locks — review stage

Depends on PR #2 opening/reconciliation. Not deployed. This is a ledger posting control, **not a complete daily/monthly accounting close or PMS night audit**.

An owner can lock a completed calendar day or full calendar month after the opening cutover. The UI requires explicit acknowledgement of this scope. Overlapping active locks are rejected; reopen overlapping daily locks before replacing them with a monthly lock. Today and incomplete months cannot be locked. A lock stores an immutable trial-balance snapshot and user/reason. Reopening appends a separate immutable event and requires a reason of 10–250 characters; it does not delete the prior lock/snapshot. Both actions use the existing audited/idempotent action engine and property row lock.

All new journal posts (manual, source imports, transfers and reversals) check the active locks within the same transaction. Exact retries of an existing journal remain safe. Source previews reject new entries within locked dates; the apply operation rechecks under the property lock. Reversals in an open later period are allowed. Database direct SQL is outside this application-level boundary.

The UI displays the latest 100 lock records and reopening reasons. End dates are exclusive. Source booking/voucher changes remain possible operationally; a lock is not evidence of full source posting, reconciliation, receivables allocation, cash completeness or tax compliance. These require a separate close-readiness workflow before advertising final closing. No profit/loss closing or retained-earnings transfer is generated.

Validation: server tests cover daily/monthly boundaries, opening prerequisite, acknowledgement, overlapping locks, owner/property isolation, retry, reversal dates and immutable reopening. Browser smoke covers lock/reopen with synthetic data only.

Next: source-completeness and reconciliation checklist/digest, explain pending sources and unresolved differences, then a separately approved accounting close. Do not deploy or lock live property periods without explicit approval.
