# Closing readiness review (read-only)

This stage depends on PRs #2 (opening/reconciliation) and #3 (ledger locks). It adds an owner-only, tenant-scoped review in the ledger workspace. It neither locks a period nor posts, approves or modifies a financial record. Its result is advisory, not a tax-compliance statement, statutory close or completed PMS night audit.

## What is checked

- An opening exists, the selected period does not predate cutover, and aggregated/unallocated customer openings are flagged.
- The selected half-open period is no longer than 370 days and contains no future days. Today can be inspected but is marked incomplete.
- Payment/refund and expense vouchers dated within the period, plus reservations with period charges, payments or checkout events, are examined through the existing posting adapters. Only planned journal dates within the selected period are counted as pending/conflicting. Adapter failures are visible blockers; no unsupported source silently passes.
- Open stays with relevant activity require review because the current adapter posts accommodation only after checkout. This is an explicit accrual limitation, not an assertion that open stays have no revenue.
- Missing/unposted sources remain detectable even inside locked dates. Actual import/post actions still enforce locks.
- Each of cash, bank and card receivables requires its latest reconciliation **on the final included date**, including zero balances. Missing, different and stale records block the limited readiness checks. A changed ledger digest invalidates the comparison even if a changed balance happens to net to zero.
- The posted trial balance must balance and use the configured currency.

At most 200 sources are scanned across all types. Total counts and inspected counts are shown. Exceeding the cap always blocks a positive result and asks the owner to narrow the period. This cap does not limit the account balance aggregation. A reservation exceeding adapter limits remains explicitly blocked. Historical adapter errors outside the selected range can conservatively block a reservation review rather than hide uncertainty.

The response includes a digest of the returned review for comparison, **not** a write-authorization token. A property row lock provides a consistent view against service-layer writes during the request; it is not retained after the request. The UI discards responses for changed properties, dates or detached views and says to rerun after changes. No readiness result is persisted as an approved close. Direct SQL and sources outside existing adapters are outside this review's completeness guarantee.

## Validation and remaining work

Server tests cover read-only behavior, exact end-date reconciliations, differences/staleness, explicit receipt posting, locked-period missing sources, changed source conflicts, open-stay limitations, scan caps, dates, owner permissions and tenant/API isolation. Browser smoke exercises the report and captures the review workspace using synthetic data.

Next: formal approval workflow with server-side readiness recheck, clear policy for open-stay accrual and outstanding customer allocation, and financial statements. A green limited check must not be treated as a final accounting close. No production deployment or live financial approvals occur in this stage.
