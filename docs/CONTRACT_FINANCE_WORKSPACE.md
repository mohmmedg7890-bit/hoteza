# Reservation, contract and finance workspace

Hoteza keeps its existing Django + PostgreSQL backend and Arabic JavaScript SPA. This update adds daily/monthly pricing, multiple simultaneous units per reservation, visit purpose, opt-in renewal, immutable numbered contract snapshots, a before-tax discount, separate expense vouchers, and booking detail/finance tabs.

## Pricing and lifecycle
- Money is stored in minor currency units. Daily and monthly rates are per unit. Monthly cycles follow the original arrival day, clamped to the calendar month's last day; partial cycles are prorated across that cycle's days, with minor-unit remainders distributed deterministically. Tax follows the property's configured percentage, rounded per charge line.
- All unit availability/capacity checks occur in the existing property-locked transaction. Confirmed reservations can add/change/remove units before financial documents exist. In-house reservations support a selected unit transfer and adding a unit. Owners can remove a remaining unit only if capacity remains sufficient and its future charges have not been invoiced; existing billed lines are never deleted. Financial edits after invoicing use linked correction documents.
- Discounts apply to the current room charges before tax, as percentage or fixed amount. Renewal/extensions do not automatically repeat an old discount. Expense vouchers are property outflows, not guest payments, and never reduce guest debt.
- Early same-day departure retains a one-night charge. An owner can settle future nights, issue invoices/refunds where necessary, then confirm same-day checkout. Existing debt, invoicing and authorization rules remain enforced.

## Official company details and terms
The property settings have an explicit preset for the business details supplied by the user (including the phone exactly as supplied). It applies only to the selected property when saved. No email is invented. Other properties are not changed.

The original fourteen terms have not been supplied. A fourteen-field settings form accepts the exact text. Contracts are visibly incomplete drafts until those fields are filled. No legal approval, Nazeel certification or official electronic-signature compliance is claimed. Signature lines support manual signing on paper.

A newly saved reservation gets a contract number and immutable snapshot. A new contract version can be issued after changes without changing old snapshots. Client sharing is blocked for incomplete contracts. For a complete snapshot, the user explicitly confirms creation of a 72-hour bearer link, then can copy it or open an email draft; no message is sent automatically. Shared views require a valid timestamped signature, have no app access, are not indexed, and do not expose authenticated export routes.

## Automatic extension
Opted-in, checked-in stays are checked every minute while the app is open. A failed availability check blocks renewal and displays a message. To run without open browsers, schedule:

    python manage.py run_auto_extensions

once per minute in the hosting environment. This command uses the same authorization, locking and idempotency path. A permanent external scheduler has not been provisioned on the current free Render instance. Enabling the field is not represented as an always-on scheduler.

## Button regression
Application dialogs use ordinary nonmodal native show/close semantics with an explicit shared veil, modal stacking, Escape and focus trapping. Native top-layer inert regions, backdrop filters, and page compositing animations are avoided so closing a dialog immediately releases pointer hit-testing. The browser regression repeatedly opens/closes guest forms and then uses real clicks on report tabs. Automatic page translation is disabled for Arabic operational templates to prevent label/markup rewriting.
