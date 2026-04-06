#!/usr/bin/env python3
"""
ICS Calendar File Generator

Takes the computed deadlines JSON and generates an .ics file that can be
imported into Outlook, Google Calendar, Apple Calendar, etc.

Usage:
    python generate_ics.py --input computed.json --output deadlines.ics

The .ics file will include:
- All-day, timed, and multi-day events
- Event descriptions with the rule basis
- Priority levels mapped to iCalendar priority values
- Attendee invitations (if email addresses are provided)
- Alarms/reminders: 7 days and 1 day before each deadline

Supported deadline fields:
- "date" (required): YYYY-MM-DD
- "time" (optional): HH:MM in 24-hour format — makes it a timed event
- "timezone" (optional): IANA timezone string, e.g. "America/Denver"
- "duration_days" (optional): integer — makes it a multi-day event
  If time is set without an explicit end time, the event ends at 17:00.
"""

import json
import sys
import argparse
import uuid
from datetime import date, datetime, timedelta


def escape_ics_text(text):
    """Escape special characters for iCalendar text values."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def priority_to_ics(priority_str):
    """Map our priority levels to iCalendar priority values.
    iCal: 1-4 = high, 5 = normal, 6-9 = low."""
    mapping = {
        "critical": 1,
        "high": 3,
        "medium": 5,
        "low": 7
    }
    return mapping.get(priority_str, 5)


def category_to_color(category):
    """Suggest calendar categories/colors based on deadline type.
    Note: actual color rendering depends on the calendar application."""
    mapping = {
        "trial": "Red Category",
        "discovery": "Blue Category",
        "experts": "Purple Category",
        "motions": "Orange Category",
        "pleadings": "Yellow Category",
        "adr": "Green Category",
        "hearing": "Red Category",
        "hearing_prep": "Orange Category",
        "award": "Red Category",
        "arbitration": "Blue Category",
        "custom": "Yellow Category",
    }
    return mapping.get(category, "Blue Category")


VTIMEZONE_AMERICA_DENVER = """BEGIN:VTIMEZONE
TZID:America/Denver
BEGIN:STANDARD
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZOFFSETFROM:-0600
TZOFFSETTO:-0700
TZNAME:MST
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZOFFSETFROM:-0700
TZOFFSETTO:-0600
TZNAME:MDT
END:DAYLIGHT
END:VTIMEZONE"""


def generate_ics(data, output_path):
    """Generate an .ics file from computed deadlines data."""
    matter = data["matter_name"]
    deadlines = data["deadlines"]
    attendees = data.get("attendees", [])

    # Check if any deadlines have timed events — if so, we need a VTIMEZONE
    has_timed_events = any(dl.get("time") for dl in deadlines)

    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Litigation Deadline Calendar//EN")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.append(f"X-WR-CALNAME:{escape_ics_text(matter)} - Deadlines")

    # Add VTIMEZONE block if any timed events exist
    if has_timed_events:
        for tz_line in VTIMEZONE_AMERICA_DENVER.strip().split("\n"):
            lines.append(tz_line)

    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for dl in deadlines:
        # Skip metadata/note entries — they're not calendar events
        if dl.get("is_note"):
            continue

        uid = str(uuid.uuid4())
        dl_date = datetime.strptime(dl["date"], "%Y-%m-%d").date()

        event_time = dl.get("time")        # e.g. "08:30"
        timezone = dl.get("timezone", "America/Denver")
        duration_days = dl.get("duration_days")  # e.g. 5

        description_parts = [
            f"Rule Basis: {dl['rule_basis']}",
            f"Category: {dl['category'].replace('_', ' ').title()}",
            f"Priority: {dl['priority'].upper()}"
        ]
        description = "\\n".join(description_parts)

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{now}")

        if event_time:
            # --- Timed event ---
            hour, minute = event_time.split(":")
            start_str = dl_date.strftime("%Y%m%d") + f"T{hour}{minute}00"
            lines.append(f"DTSTART;TZID={timezone}:{start_str}")

            if duration_days and duration_days > 1:
                # Multi-day timed event: ends at 17:00 on the last day
                end_date = dl_date + timedelta(days=duration_days - 1)
                end_str = end_date.strftime("%Y%m%d") + "T170000"
            else:
                # Single-day timed event: ends at 17:00 same day
                end_str = dl_date.strftime("%Y%m%d") + "T170000"

            lines.append(f"DTEND;TZID={timezone}:{end_str}")

        elif duration_days and duration_days > 1:
            # --- Multi-day all-day event ---
            dtstart = dl_date.strftime("%Y%m%d")
            dtend = (dl_date + timedelta(days=duration_days)).strftime("%Y%m%d")
            lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
            lines.append(f"DTEND;VALUE=DATE:{dtend}")

        else:
            # --- Single all-day event (default) ---
            dtstart = dl_date.strftime("%Y%m%d")
            dtend = (dl_date + timedelta(days=1)).strftime("%Y%m%d")
            lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
            lines.append(f"DTEND;VALUE=DATE:{dtend}")

        lines.append(f"SUMMARY:{escape_ics_text(dl['description'])}")
        lines.append(f"DESCRIPTION:{escape_ics_text(description)}")
        lines.append(f"PRIORITY:{priority_to_ics(dl['priority'])}")
        lines.append(f"CATEGORIES:{category_to_color(dl['category'])}")
        lines.append("TRANSP:TRANSPARENT")  # Don't block the calendar

        # Add attendees
        for email in attendees:
            lines.append(f"ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION;CN={email}:mailto:{email}")

        # Add reminders: 7 days before and 1 day before
        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-P7D")
        lines.append("ACTION:DISPLAY")
        lines.append(f"DESCRIPTION:7 days until: {escape_ics_text(dl['description'])}")
        lines.append("END:VALARM")

        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-P1D")
        lines.append("ACTION:DISPLAY")
        lines.append(f"DESCRIPTION:TOMORROW: {escape_ics_text(dl['description'])}")
        lines.append("END:VALARM")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # Write the file with CRLF line endings (required by iCalendar spec)
    with open(output_path, "w", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")

    event_count = sum(1 for dl in deadlines if not dl.get("is_note"))
    print(f"Generated .ics file with {event_count} events: {output_path}")
    print(f"Matter: {matter}")
    if attendees:
        print(f"Attendees: {', '.join(attendees)}")
    print(f"\nTo use: Import this file into Outlook, Google Calendar, or Apple Calendar.")


def main():
    parser = argparse.ArgumentParser(description="Generate .ics calendar file from computed deadlines")
    parser.add_argument("--input", required=True, help="Path to computed deadlines JSON file")
    parser.add_argument("--output", required=True, help="Path for output .ics file")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)

    generate_ics(data, args.output)


if __name__ == "__main__":
    main()
