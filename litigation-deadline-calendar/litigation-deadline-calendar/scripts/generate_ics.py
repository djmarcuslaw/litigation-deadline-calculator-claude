#!/usr/bin/env python3
"""
ICS Calendar File Generator

Takes the computed deadlines JSON and generates an .ics file that can be
imported into Outlook, Google Calendar, Apple Calendar, etc.

Usage:
    python generate_ics.py --input computed.json --output deadlines.ics

The .ics file will include:
- All-day events for each deadline
- Event descriptions with the rule basis
- Priority levels mapped to iCalendar priority values
- Attendee invitations (if email addresses are provided)
- Alarms/reminders: 7 days and 1 day before each deadline
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


def generate_ics(data, output_path):
    """Generate an .ics file from computed deadlines data."""
    matter = data["matter_name"]
    deadlines = data["deadlines"]
    attendees = data.get("attendees", [])
    disclaimer = data.get("disclaimer", "")

    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Litigation Deadline Calendar//EN")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.append(f"X-WR-CALNAME:{escape_ics_text(matter)} - Deadlines")

    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for dl in deadlines:
        uid = str(uuid.uuid4())
        dl_date = datetime.strptime(dl["date"], "%Y-%m-%d").date()
        next_day = dl_date + timedelta(days=1)

        # Format dates for all-day events (DATE value, not DATE-TIME)
        dtstart = dl_date.strftime("%Y%m%d")
        dtend = next_day.strftime("%Y%m%d")

        description_parts = [
            f"Rule Basis: {dl['rule_basis']}",
            f"Category: {dl['category'].replace('_', ' ').title()}",
            f"Priority: {dl['priority'].upper()}",
            "",
            disclaimer
        ]
        description = "\\n".join(description_parts)

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{now}")
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
        # 7-day reminder
        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-P7D")
        lines.append("ACTION:DISPLAY")
        lines.append(f"DESCRIPTION:7 days until: {escape_ics_text(dl['description'])}")
        lines.append("END:VALARM")

        # 1-day reminder
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

    print(f"Generated .ics file with {len(deadlines)} events: {output_path}")
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
