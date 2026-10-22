# SyncStay interface adaptation

Hoteza remains an independent Django application. This change adapts the visual and reception workflow patterns from the user's SyncStay reference without copying its runtime, database, accounts or hosting configuration.

- Light RTL sidebar with SVG icons, grouped navigation and property context; all 15 Hoteza screens remain accessible.
- Overview and operations shortcuts link to the same reservation, payment and invoice actions.
- Reservations, calendar, daily operations and units share navigation tabs.
- Reservation status and source filters combine with the existing search.
- Booking dialog sections for guest and stay, quick durations (1 / 7 / 30 nights), synchronized nights/departure, live pre-tax and tax-inclusive estimate, and booking/maintenance conflict hints. The server remains authoritative at save time.
- Add a guest from the booking dialog, return to the draft and select the newly created guest.
- Manual refresh reloads current property data; mobile navigation and print rules retained.

This does not migrate SyncStay records or add its unimplemented channel connections, detailed identity attachments, channel configuration or category-level booking mode. Existing Hoteza reservation, checkout, invoice, receipt and export services remain in place.

Local validation: JavaScript syntax and diff whitespace checks; Django suite 36 tests, 35 passed and PostgreSQL-specific concurrency test skipped on SQLite. CI runs the full PostgreSQL suite and browser workflow, including the new navigation, filters, booking duration/estimate and guest-return flow.
