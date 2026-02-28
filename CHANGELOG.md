# Changelog

## 0.2.0 — 2026-02-27

### Changed
- Jurisdiction is now always asked explicitly. The skill no longer defaults to Colorado; it prompts for jurisdiction every time.
- Written discovery deadlines (Interrogatories, RFPs, RFAs) are now combined into a single calendar entry instead of three separate entries with identical dates.
- Disclaimer removed from computed output and calendar event descriptions.

### Added
- Source citation requirement: the skill now provides URLs to the official rule texts used in each calculation, both during verification and in the final output.
- Timed event support: deadline entries can include a `time` field (HH:MM) and `timezone` field (IANA string) to create timed calendar events instead of all-day events. Events without an explicit end time default to 17:00.
- Multi-day event support: deadline entries can include a `duration_days` field to span multiple days (e.g., a 5-day trial). Works with both timed and all-day events.
- VTIMEZONE block (America/Denver) is automatically included in the .ics file when any timed events are present.

## 0.1.0 — 2026-02-27

Initial release.

- Colorado CRCP rules built in (Rule 6 time computation, Rules 26/33/34/36 discovery, Rule 56 summary judgment, expert disclosures)
- Federal FRCP rules built in
- AAA Commercial and Employment arbitration rules
- JAMS Comprehensive and Streamlined arbitration rules
- PDF scheduling order parsing
- Backward deadline computation from scheduling order dates
- .ics calendar file generation with Outlook import support
- Calendar entry format: Matter Name — Deadline Description
- Attendee/invite support via .ics ATTENDEE fields
- Automatic reminders at 7 days and 1 day before each deadline
- Rule verification step that checks for recent amendments before computing
- Holiday calendar computation with observed-date logic
