# Guest registration and hotel reports

Guest registration now uses three sections: personal details, identity information, contact/address. First and last names form the existing full name, with optional second/middle and English variants. Required fields are checked in the browser and on the server. Existing guest records remain unchanged until edited; no birth dates or identity numbers are invented.

Birth dates use Gregorian input and server-derived Umm al-Qura Hijri dates (hijridate 2.3.0; supported Gregorian dates begin 1924-08-01). The identity check verifies formatting only, without external government verification. Existing strict Saudi mobile, email, and detailed address rules remain in place.

Optional photos are scaled in the browser, checked/re-encoded as JPEG by the server, stripped of metadata, stored in PostgreSQL, and served only to members of the guest's property. No uploads depend on Render's ephemeral local disk. Photo display in bookings requires the profile checkbox. Logical backups include the binary photo field using Django's serialization.

Report views: operational overview, daily movement, unit performance, booking sources. Date presets and applied period drive on-screen data and all six export formats. Exports remain linked to the displayed/applied period when date inputs change before applying. Print layout includes property, report title, period, currency and calculation notes. No expense/profit/night-audit features are implied.

Validation: server tests for identity/birth data, persistence, optional photos, tenant isolation and selected exports; browser smoke test covers registration, return to booking, Hijri conversion, report period, view switching and export links alongside the existing operational flow.
