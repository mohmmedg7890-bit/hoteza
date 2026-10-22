# Glass interface and validated bookings

- Root `/` is now the public glass landing page. `/app/` retains the authenticated operations application. The landing's illustrated metrics and subscription modal are clearly labelled examples; no purchase or subscription request is sent.
- Dark/light glass styling across operation screens, login and forms; persistent browser-only accent, radius and glow controls. Paper documents retain their print styling.
- Native confirmation dialogs replaced with accessible in-app confirmation. Existing CSRF, property membership, transactional booking and invoicing services retained.
- Guest name requires two or more letter-based components. Saudi phone accepts `05` + eight digits, or `+9665` + eight digits, including Arabic digit normalization, and stores canonical international format. This checks format, not ownership or deliverability.
- Email, region, city and street/short-address required for guest saves and new bookings. Existing records and bookings are preserved; incomplete legacy guests must be completed when creating a new booking. Guest detail edits inside booking save within the same transaction. Saving the booking updates the selected guest's shared profile, as disclosed in the form.
- Separate expected arrival/departure times, defaults 14:00 and 12:00, displayed as half-hour options (retaining any already-stored valid time). These are expected hotel times, not hourly inventory slots. Overnight availability remains checked by date on the server. No arrival-in-the-past or overlapping allocation permitted.
- Live accessible feedback, focus on first invalid field, inline hints, LTR phone/email/date fields in RTL layout, saving state and server-confirmed success notification.
- Internal navigation stays client-side; downloads, document links, login/logout and genuine external navigation retain their intended behavior. Reduced-motion preference respected.

Tests extend the operational browser workflow to landing modals, dark/light settings, persistence, invalid phone blocking, and in-app confirmation. Backend coverage includes required guest fields, phone normalization, malformed expected time and rollback on conflict. No live guest data is used for these tests.
