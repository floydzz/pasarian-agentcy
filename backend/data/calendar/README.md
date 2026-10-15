# Reviewed Malaysian calendar data

The application imports these records locally. It never asks a language model for authoritative dates and never downloads a holiday feed while rendering the calendar.

- `malaysia-2026.json`: 49 distinct published federal/state occasion records from BKPP's combined 2026 schedule.
- `malaysia-2027.json`: 50 distinct occasion records from 52 combined schedule rows; identical occasion/date pairs merge their state applicability.
- `school-2026.json` and `school-2027.json`: four school-break periods for each of Groups A and B from the KPM academic calendars. Group A covers Kedah, Kelantan and Terengganu; Group B covers the other states/territories.

The original publications were inspected on 14 October 2026. Source URLs are retained per record. Published dates qualified as subject to change retain `tentative` status. Publication status describes the imported schedule, not a claim that a later official confirmation was checked automatically.

To update, inspect the original publication and relevant amendments, edit the affected record while keeping its stable `source_key`, update verification metadata, and run `python scripts/import_calendar.py`. The importer adds a content revision digest. Existing plans then expose the previous and current source dates and require review before campaign conversion. A withdrawal should set `publication_status` to `withdrawn`; removing a record from a file deliberately does not delete saved provenance.

Observed replacements and ad hoc declarations must be added as separately sourced records, with `observed_for` linking their original source key where applicable. They are not generated from a general weekend assumption. The application exposes this coverage limit. Festival periods and commercial occasions should use their own categories and sources, never impersonate public holidays.
