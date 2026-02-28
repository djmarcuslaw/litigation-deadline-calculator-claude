#!/usr/bin/env python3
"""
Litigation Deadline Calculator

Computes backward deadlines from scheduling order dates based on the applicable
rules of civil procedure (Colorado CRCP, Federal FRCP) or arbitration rules
(AAA, JAMS).

Usage:
    python compute_deadlines.py --input deadlines.json --jurisdiction colorado --output computed.json
    python compute_deadlines.py --input deadlines.json --forum aaa_commercial --output computed.json

Input JSON format:
{
    "matter_name": "Smith v. Jones Co.",
    "proceeding_type": "litigation" | "arbitration",
    "jurisdiction": "colorado" | "federal" | "<state_name>",
    "forum": "aaa_commercial" | "aaa_employment" | "jams_comprehensive" | "jams_streamlined",
    "service_method": "electronic" | "mail" | "hand",
    "scheduling_order_dates": {
        "trial_date": "2026-09-15",
        "discovery_cutoff": "2026-07-28",
        "dispositive_motion_deadline": "2026-06-15",
        "pretrial_conference": "2026-08-15",
        "plaintiff_expert_disclosure": null,
        "defendant_expert_disclosure": null,
        "rebuttal_expert_disclosure": null,
        "amend_pleadings_deadline": "2026-03-15",
        "join_parties_deadline": "2026-03-15",
        "mediation_deadline": "2026-05-01",
        "hearing_date": null,
        "custom_dates": {
            "Motions in Limine": "2026-08-01"
        }
    },
    "attendees": ["jane@company.com", "bob@lawfirm.com"]
}

Output JSON: list of deadline objects with description, date, rule_basis, category, priority
"""

import json
import sys
import argparse
from datetime import date, timedelta, datetime


# ---------------------------------------------------------------------------
# Holiday computation
# ---------------------------------------------------------------------------

def nth_weekday(year, month, weekday, n):
    """Return the nth occurrence of a weekday in a given month.
    weekday: 0=Monday, 6=Sunday. n: 1-based."""
    first_day = date(year, month, 1)
    first_weekday = first_day.weekday()
    diff = (weekday - first_weekday) % 7
    return first_day + timedelta(days=diff + 7 * (n - 1))


def last_weekday(year, month, weekday):
    """Return the last occurrence of a weekday in a given month."""
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    diff = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=diff)


def get_federal_holidays(year):
    """Return a set of observed federal holiday dates for a given year."""
    holidays = set()

    raw_holidays = [
        date(year, 1, 1),                          # New Year's Day
        nth_weekday(year, 1, 0, 3),                 # MLK Day (3rd Monday Jan)
        nth_weekday(year, 2, 0, 3),                 # Presidents' Day (3rd Monday Feb)
        last_weekday(year, 5, 0),                   # Memorial Day (last Monday May)
        date(year, 6, 19),                          # Juneteenth
        date(year, 7, 4),                           # Independence Day
        nth_weekday(year, 9, 0, 1),                 # Labor Day (1st Monday Sep)
        nth_weekday(year, 10, 0, 2),                # Columbus Day (2nd Monday Oct)
        date(year, 11, 11),                         # Veterans Day
        nth_weekday(year, 11, 3, 4),                # Thanksgiving (4th Thursday Nov)
        date(year, 12, 25),                         # Christmas
    ]

    for h in raw_holidays:
        # Observe on Friday if Saturday, Monday if Sunday
        if h.weekday() == 5:  # Saturday
            holidays.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday
            holidays.add(h + timedelta(days=1))
        else:
            holidays.add(h)

    return holidays


def get_colorado_holidays(year):
    """Return a set of observed Colorado legal holidays for a given year.
    Colorado holidays are the same as federal holidays minus Juneteenth
    (not listed in CRCP Rule 6), plus any day the court is closed."""
    holidays = get_federal_holidays(year)
    # Colorado Rule 6 lists the same holidays as federal except Juneteenth
    # is not explicitly listed. However, Colorado courts have generally
    # observed Juneteenth since it became a federal holiday. We include it
    # for safety. The verification step will flag if this changes.
    return holidays


def get_holidays(year, jurisdiction):
    """Get the holiday set for a jurisdiction and year."""
    if jurisdiction == "federal":
        return get_federal_holidays(year)
    elif jurisdiction == "colorado":
        return get_colorado_holidays(year)
    else:
        # For other jurisdictions, default to federal holidays.
        # The skill should prompt the user to verify.
        return get_federal_holidays(year)


# ---------------------------------------------------------------------------
# Time computation per jurisdiction
# ---------------------------------------------------------------------------

def is_business_day(d, holidays):
    """Check if a date is a business day (not weekend, not holiday)."""
    return d.weekday() < 5 and d not in holidays


def next_business_day(d, holidays):
    """If d is not a business day, advance to the next one."""
    while not is_business_day(d, holidays):
        d += timedelta(days=1)
    return d


def compute_deadline_colorado(start_date, days, holidays):
    """Compute a deadline under Colorado CRCP Rule 6.

    - Exclude the trigger day.
    - If period < 11 days and not specified as 'calendar days':
      exclude intermediate Sat/Sun/holidays.
    - If period >= 11 days: count every day.
    - If last day is Sat/Sun/holiday: extend to next business day.
    """
    if days < 11:
        # Exclude intermediate weekends and holidays
        current = start_date
        counted = 0
        while counted < days:
            current += timedelta(days=1)
            if is_business_day(current, holidays):
                counted += 1
        return current
    else:
        # Count every day
        deadline = start_date + timedelta(days=days)
        return next_business_day(deadline, holidays)


def compute_deadline_federal(start_date, days, holidays):
    """Compute a deadline under FRCP Rule 6.

    - Exclude the trigger day.
    - Count every day (including weekends and holidays).
    - If last day is Sat/Sun/holiday: extend to next business day.
    """
    deadline = start_date + timedelta(days=days)
    return next_business_day(deadline, holidays)


def compute_deadline_calendar(start_date, days, holidays):
    """Simple calendar day computation for arbitration.
    Count calendar days, extend to next business day if last day is non-business."""
    deadline = start_date + timedelta(days=days)
    return next_business_day(deadline, holidays)


def compute_backward_date(anchor_date, days, jurisdiction, holidays):
    """Compute a date that is 'days' before the anchor date.

    For backward computation (e.g., 'serve interrogatories at least X days
    before discovery cutoff'), we subtract days and then adjust if the
    resulting date is not a business day (move EARLIER, not later).
    """
    target = anchor_date - timedelta(days=days)
    # For backward deadlines, if the target falls on a non-business day,
    # move to the PRECEDING business day (earlier, to be safe)
    while not is_business_day(target, holidays):
        target -= timedelta(days=1)
    return target


def compute_deadline(start_date, days, jurisdiction, holidays):
    """Route to the appropriate deadline computation method."""
    if jurisdiction == "colorado":
        return compute_deadline_colorado(start_date, days, holidays)
    elif jurisdiction == "federal":
        return compute_deadline_federal(start_date, days, holidays)
    else:
        # Default to federal-style counting for other jurisdictions
        return compute_deadline_federal(start_date, days, holidays)


# ---------------------------------------------------------------------------
# Service method adjustment
# ---------------------------------------------------------------------------

def service_days(jurisdiction, method):
    """Return additional days to add based on service method."""
    if method == "mail":
        return 3  # Both CRCP 6(e) and FRCP 6(d) add 3 days for mail
    elif method == "electronic":
        if jurisdiction == "federal":
            return 3  # FRCP 6(d) adds 3 days for e-service
        else:
            return 0  # Colorado: no additional days for e-service
    else:  # hand delivery
        return 0


# ---------------------------------------------------------------------------
# Litigation deadline generation
# ---------------------------------------------------------------------------

def generate_litigation_deadlines(data):
    """Generate all computed deadlines for a litigation matter."""
    jurisdiction = data.get("jurisdiction", "colorado")
    svc_method = data.get("service_method", "electronic")
    dates = data["scheduling_order_dates"]
    matter = data["matter_name"]

    # Collect all years we might need holidays for
    all_dates_raw = [v for v in dates.values() if isinstance(v, str)]
    if dates.get("custom_dates"):
        all_dates_raw.extend(dates["custom_dates"].values())
    years_needed = set()
    for d in all_dates_raw:
        try:
            years_needed.add(datetime.strptime(d, "%Y-%m-%d").year)
        except (ValueError, TypeError):
            pass
    # Also include current year and next year
    years_needed.add(date.today().year)
    years_needed.add(date.today().year + 1)

    holidays = set()
    for y in years_needed:
        holidays.update(get_holidays(y, jurisdiction))

    svc_extra = service_days(jurisdiction, svc_method)
    deadlines = []

    def parse_date(s):
        if s:
            return datetime.strptime(s, "%Y-%m-%d").date()
        return None

    trial_date = parse_date(dates.get("trial_date"))
    discovery_cutoff = parse_date(dates.get("discovery_cutoff"))
    disp_motion_deadline = parse_date(dates.get("dispositive_motion_deadline"))
    pretrial_conf = parse_date(dates.get("pretrial_conference"))
    plaintiff_expert = parse_date(dates.get("plaintiff_expert_disclosure"))
    defendant_expert = parse_date(dates.get("defendant_expert_disclosure"))
    rebuttal_expert = parse_date(dates.get("rebuttal_expert_disclosure"))
    amend_deadline = parse_date(dates.get("amend_pleadings_deadline"))
    join_deadline = parse_date(dates.get("join_parties_deadline"))
    mediation_deadline = parse_date(dates.get("mediation_deadline"))

    # --- Scheduling order dates (direct entries) ---
    if trial_date:
        deadlines.append({
            "description": f"{matter} — Trial Date",
            "date": trial_date.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "trial",
            "priority": "critical"
        })

    if discovery_cutoff:
        deadlines.append({
            "description": f"{matter} — Discovery Cutoff",
            "date": discovery_cutoff.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "discovery",
            "priority": "critical"
        })

    if disp_motion_deadline:
        deadlines.append({
            "description": f"{matter} — Dispositive Motion Filing Deadline",
            "date": disp_motion_deadline.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "motions",
            "priority": "critical"
        })

    if pretrial_conf:
        deadlines.append({
            "description": f"{matter} — Pretrial Conference",
            "date": pretrial_conf.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "trial",
            "priority": "high"
        })

    if amend_deadline:
        deadlines.append({
            "description": f"{matter} — Deadline to Amend Pleadings",
            "date": amend_deadline.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "pleadings",
            "priority": "high"
        })

    if join_deadline:
        deadlines.append({
            "description": f"{matter} — Deadline to Join Parties",
            "date": join_deadline.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "pleadings",
            "priority": "high"
        })

    if mediation_deadline:
        deadlines.append({
            "description": f"{matter} — Mediation Deadline",
            "date": mediation_deadline.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "adr",
            "priority": "high"
        })

    # Custom dates from the scheduling order
    custom_dates = dates.get("custom_dates", {})
    for label, dt_str in custom_dates.items():
        dt = parse_date(dt_str)
        if dt:
            deadlines.append({
                "description": f"{matter} — {label}",
                "date": dt.isoformat(),
                "rule_basis": "Scheduling Order",
                "category": "custom",
                "priority": "high"
            })

    # --- Backward-computed deadlines ---

    if jurisdiction == "colorado":
        response_days = 35
        expert_p = 126  # plaintiff expert: 126 days before trial
        expert_d = 98   # defendant expert: 98 days before trial
        expert_r = 63   # rebuttal expert: 63 days before trial
        disco_cutoff_default = 49  # days before trial
        summary_j_response = 35
        summary_j_reply = 14
        rule_prefix = "CRCP"
    elif jurisdiction == "federal":
        response_days = 30
        expert_p = 90   # 90 days before trial
        expert_d = 90   # same for defendant (rebuttal is 30 days after)
        expert_r = 30   # 30 days after opposing disclosure (relative)
        disco_cutoff_default = 0  # set by scheduling order
        summary_j_response = 21  # varies by local rule
        summary_j_reply = 14
        rule_prefix = "FRCP"
    else:
        # Default to federal
        response_days = 30
        expert_p = 90
        expert_d = 90
        expert_r = 30
        disco_cutoff_default = 0
        summary_j_response = 21
        summary_j_reply = 14
        rule_prefix = "Rules of Civil Procedure"

    effective_response_days = response_days + svc_extra

    # Expert disclosure deadlines (use scheduling order if provided, else compute from trial)
    if trial_date:
        if not plaintiff_expert:
            pe_date = compute_backward_date(trial_date, expert_p, jurisdiction, holidays)
            deadlines.append({
                "description": f"{matter} — Plaintiff Expert Disclosure Deadline",
                "date": pe_date.isoformat(),
                "rule_basis": f"{rule_prefix} Rule 26(a)(2) ({expert_p} days before trial)",
                "category": "experts",
                "priority": "critical"
            })
        else:
            deadlines.append({
                "description": f"{matter} — Plaintiff Expert Disclosure Deadline",
                "date": plaintiff_expert.isoformat(),
                "rule_basis": "Scheduling Order",
                "category": "experts",
                "priority": "critical"
            })

        if not defendant_expert:
            if jurisdiction == "colorado":
                de_date = compute_backward_date(trial_date, expert_d, jurisdiction, holidays)
            else:
                de_date = compute_backward_date(trial_date, expert_d, jurisdiction, holidays)
            deadlines.append({
                "description": f"{matter} — Defendant Expert Disclosure Deadline",
                "date": de_date.isoformat(),
                "rule_basis": f"{rule_prefix} Rule 26(a)(2) ({expert_d} days before trial)",
                "category": "experts",
                "priority": "critical"
            })
        else:
            deadlines.append({
                "description": f"{matter} — Defendant Expert Disclosure Deadline",
                "date": defendant_expert.isoformat(),
                "rule_basis": "Scheduling Order",
                "category": "experts",
                "priority": "critical"
            })

        if not rebuttal_expert:
            if jurisdiction == "colorado":
                re_date = compute_backward_date(trial_date, expert_r, jurisdiction, holidays)
            elif jurisdiction == "federal" and defendant_expert:
                # Federal: 30 days after opposing party's disclosure
                re_date = compute_deadline(defendant_expert, expert_r, jurisdiction, holidays)
            else:
                re_date = compute_backward_date(trial_date, expert_r if jurisdiction == "colorado" else 60, jurisdiction, holidays)
            deadlines.append({
                "description": f"{matter} — Rebuttal Expert Disclosure Deadline",
                "date": re_date.isoformat(),
                "rule_basis": f"{rule_prefix} Rule 26(a)(2)",
                "category": "experts",
                "priority": "high"
            })
        else:
            deadlines.append({
                "description": f"{matter} — Rebuttal Expert Disclosure Deadline",
                "date": rebuttal_expert.isoformat(),
                "rule_basis": "Scheduling Order",
                "category": "experts",
                "priority": "high"
            })

    # Discovery backward deadlines
    disco_anchor = discovery_cutoff
    if not disco_anchor and trial_date and disco_cutoff_default > 0:
        disco_anchor = compute_backward_date(trial_date, disco_cutoff_default, jurisdiction, holidays)
        deadlines.append({
            "description": f"{matter} — Discovery Cutoff (Computed)",
            "date": disco_anchor.isoformat(),
            "rule_basis": f"{rule_prefix} Rule 16(b)(11) ({disco_cutoff_default} days before trial)",
            "category": "discovery",
            "priority": "critical"
        })

    if disco_anchor:
        # Last day to serve written discovery (interrogatories, RFPs, RFAs)
        last_written_disco = compute_backward_date(disco_anchor, effective_response_days, jurisdiction, holidays)
        deadlines.append({
            "description": f"{matter} — Last Day to Serve Written Discovery (Interrogatories, RFPs, RFAs)",
            "date": last_written_disco.isoformat(),
            "rule_basis": f"{rule_prefix} Rules 33/34/36 ({response_days}-day response period, must complete before discovery cutoff; RFA non-response = deemed admitted)",
            "category": "discovery",
            "priority": "critical"
        })

        # Last day to notice depositions (14-day reasonable notice)
        last_depo = compute_backward_date(disco_anchor, 14, jurisdiction, holidays)
        deadlines.append({
            "description": f"{matter} — Last Day to Notice Depositions",
            "date": last_depo.isoformat(),
            "rule_basis": f"{rule_prefix} Rule 30 (14-day reasonable notice, must complete before discovery cutoff)",
            "category": "discovery",
            "priority": "high"
        })

    # Dispositive motion response/reply deadlines
    if disp_motion_deadline:
        response_date = compute_deadline(disp_motion_deadline, summary_j_response + svc_extra, jurisdiction, holidays)
        deadlines.append({
            "description": f"{matter} — Dispositive Motion Response Due (if filed on deadline)",
            "date": response_date.isoformat(),
            "rule_basis": f"{rule_prefix} Rule 56 ({summary_j_response}-day response period)",
            "category": "motions",
            "priority": "high"
        })

        reply_date = compute_deadline(response_date, summary_j_reply + svc_extra, jurisdiction, holidays)
        deadlines.append({
            "description": f"{matter} — Dispositive Motion Reply Due (if response filed on deadline)",
            "date": reply_date.isoformat(),
            "rule_basis": f"{rule_prefix} Rule 56 ({summary_j_reply}-day reply period)",
            "category": "motions",
            "priority": "medium"
        })

    # Sort all deadlines by date
    deadlines.sort(key=lambda x: x["date"])

    return deadlines


def generate_arbitration_deadlines(data):
    """Generate deadlines for an arbitration matter.
    For arbitration, we primarily extract the scheduling order dates and
    add forum-specific procedural deadlines."""
    forum = data.get("forum", "aaa_commercial")
    dates = data["scheduling_order_dates"]
    matter = data["matter_name"]

    holidays = set()
    for y in range(date.today().year, date.today().year + 2):
        holidays.update(get_federal_holidays(y))

    deadlines = []

    def parse_date(s):
        if s:
            return datetime.strptime(s, "%Y-%m-%d").date()
        return None

    hearing_date = parse_date(dates.get("hearing_date")) or parse_date(dates.get("trial_date"))
    discovery_cutoff = parse_date(dates.get("discovery_cutoff"))

    # Scheduling order dates (extract as-is)
    if hearing_date:
        deadlines.append({
            "description": f"{matter} — Arbitration Hearing",
            "date": hearing_date.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "hearing",
            "priority": "critical"
        })

    if discovery_cutoff:
        deadlines.append({
            "description": f"{matter} — Discovery/Information Exchange Cutoff",
            "date": discovery_cutoff.isoformat(),
            "rule_basis": "Scheduling Order",
            "category": "discovery",
            "priority": "critical"
        })

    # Custom dates from the scheduling order
    custom_dates = dates.get("custom_dates", {})
    for label, dt_str in custom_dates.items():
        dt = parse_date(dt_str)
        if dt:
            deadlines.append({
                "description": f"{matter} — {label}",
                "date": dt.isoformat(),
                "rule_basis": "Arbitrator's Scheduling Order",
                "category": "custom",
                "priority": "high"
            })

    # Other explicitly listed dates
    for field, label in [
        ("dispositive_motion_deadline", "Dispositive Motion Deadline"),
        ("pretrial_conference", "Pre-Hearing Conference"),
        ("plaintiff_expert_disclosure", "Claimant Expert Disclosure"),
        ("defendant_expert_disclosure", "Respondent Expert Disclosure"),
        ("rebuttal_expert_disclosure", "Rebuttal Expert Disclosure"),
        ("amend_pleadings_deadline", "Deadline to Amend Claims"),
        ("mediation_deadline", "Mediation Deadline"),
    ]:
        dt = parse_date(dates.get(field))
        if dt:
            deadlines.append({
                "description": f"{matter} — {label}",
                "date": dt.isoformat(),
                "rule_basis": "Arbitrator's Scheduling Order",
                "category": "arbitration",
                "priority": "high"
            })

    # Forum-specific procedural deadlines
    if hearing_date:
        if "aaa" in forum:
            # AAA: Award due within 30 days after close of hearing
            award_deadline = compute_deadline_calendar(hearing_date, 30, holidays)
            deadlines.append({
                "description": f"{matter} — Arbitration Award Deadline",
                "date": award_deadline.isoformat(),
                "rule_basis": "AAA Rule R-43 (30 days after hearing close)",
                "category": "award",
                "priority": "high"
            })

            # Pre-hearing exhibit exchange (if not set in scheduling order)
            if "exhibit" not in str(custom_dates).lower():
                exhibit_date = compute_backward_date(hearing_date, 14, "federal", holidays)
                deadlines.append({
                    "description": f"{matter} — Pre-Hearing Exhibit Exchange (suggested)",
                    "date": exhibit_date.isoformat(),
                    "rule_basis": "AAA common practice (14 days before hearing)",
                    "category": "hearing_prep",
                    "priority": "medium"
                })

        elif "jams" in forum:
            # JAMS: Award due within 30 days after hearing close
            award_deadline = compute_deadline_calendar(hearing_date, 30, holidays)
            deadlines.append({
                "description": f"{matter} — Arbitration Award Deadline",
                "date": award_deadline.isoformat(),
                "rule_basis": "JAMS Rule 24 (30 days after hearing close)",
                "category": "award",
                "priority": "high"
            })

            # Pre-hearing briefs
            if "brief" not in str(custom_dates).lower():
                brief_date = compute_backward_date(hearing_date, 14, "federal", holidays)
                deadlines.append({
                    "description": f"{matter} — Pre-Hearing Briefs Due (suggested)",
                    "date": brief_date.isoformat(),
                    "rule_basis": "JAMS common practice (14 days before hearing)",
                    "category": "hearing_prep",
                    "priority": "medium"
                })

            # Witness lists
            if "witness" not in str(custom_dates).lower():
                witness_date = compute_backward_date(hearing_date, 14, "federal", holidays)
                deadlines.append({
                    "description": f"{matter} — Witness List Due (suggested)",
                    "date": witness_date.isoformat(),
                    "rule_basis": "JAMS common practice (14 days before hearing)",
                    "category": "hearing_prep",
                    "priority": "medium"
                })

    # Sort by date
    deadlines.sort(key=lambda x: x["date"])
    return deadlines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compute litigation/arbitration deadlines")
    parser.add_argument("--input", required=True, help="Path to input JSON file")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)

    proceeding_type = data.get("proceeding_type", "litigation")

    if proceeding_type == "arbitration":
        deadlines = generate_arbitration_deadlines(data)
    else:
        deadlines = generate_litigation_deadlines(data)

    result = {
        "matter_name": data["matter_name"],
        "proceeding_type": proceeding_type,
        "jurisdiction": data.get("jurisdiction", ""),
        "forum": data.get("forum", ""),
        "service_method": data.get("service_method", "electronic"),
        "generated_date": date.today().isoformat(),
        "deadlines": deadlines,
        "attendees": data.get("attendees", []),
        "disclaimer": ""
    }

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Computed {len(deadlines)} deadlines for '{data['matter_name']}'")
    print(f"Output written to: {args.output}")

    # Print summary
    for dl in deadlines:
        priority_marker = "!!!" if dl["priority"] == "critical" else "! " if dl["priority"] == "high" else "  "
        print(f"  {priority_marker} {dl['date']}  {dl['description']}")


if __name__ == "__main__":
    main()
