---
name: litigation-deadline-calendar
description: >
  Calendar litigation and arbitration deadlines from a scheduling order.
  Parses a PDF scheduling order, identifies key dates, computes backward
  deadlines using the applicable rules (Colorado CRCP, Federal FRCP, or
  arbitration forum rules for AAA/JAMS), and generates an .ics calendar file
  for Outlook import.

  Use this skill whenever the user mentions: litigation deadlines, scheduling
  order, case management order, deadline calendaring, discovery deadlines,
  trial preparation deadlines, arbitration scheduling, or anything related
  to computing or tracking court or arbitration deadlines. Also trigger when
  the user uploads a PDF that appears to be a court scheduling order or
  arbitration scheduling order.
---

# Litigation Deadline Calendar

This skill takes a scheduling order (PDF upload), determines the applicable
procedural rules, extracts key dates, computes all backward deadlines, and
generates an .ics calendar file the user can import into Outlook.

## Quick Start Workflow

1. **Gather information** from the user
2. **Parse the scheduling order** PDF
3. **Verify the rules** are current
4. **Compute deadlines** using the scripts
5. **Generate .ics file** and deliver to user

---

## Step 1: Gather Information

Ask the user for the following. They may provide some of this upfront; fill
in what you have and ask for the rest.

**Required:**
- The scheduling order PDF (uploaded file)
- Matter name (how the user wants it displayed on calendar entries, e.g., "Smith v. Jones Co.")
- Proceeding type: **litigation** or **arbitration**

**If litigation:**
- Jurisdiction: Colorado (default), Federal, or specify another state
- Service method: defaults to electronic (no extra days in Colorado, +3 in federal)

**If arbitration:**
- Forum: AAA Commercial, AAA Employment, JAMS Comprehensive, or JAMS Streamlined

**Optional:**
- Attendee email addresses (people to invite to the calendar entries)
- Any deadlines they already know are unusual or modified by the court

Present this as a simple conversation, not a form. For example:
"What's the matter name as you'd like it to appear on calendar entries?"
"Is this litigation or arbitration?"
"Which jurisdiction?" (default to Colorado if they don't specify)

---

## Step 2: Parse the Scheduling Order

Read the uploaded PDF using the Read tool. Extract every date mentioned in the
order along with what it represents. Common dates to look for:

**Litigation scheduling orders typically include:**
- Trial date
- Discovery cutoff / completion date
- Dispositive motion deadline
- Pretrial / trial preparation conference date
- Deadline to amend pleadings
- Deadline to join parties
- Plaintiff expert disclosure deadline
- Defendant expert disclosure deadline
- Rebuttal expert disclosure deadline
- Mediation deadline
- Motions in limine deadline
- Proposed jury instructions deadline
- Witness and exhibit list deadline

**Arbitration scheduling orders typically include:**
- Hearing date(s)
- Discovery / information exchange cutoff
- Expert disclosure deadlines
- Pre-hearing brief deadline
- Exhibit exchange deadline
- Witness list deadline
- Dispositive motion deadline (if permitted)
- Mediation deadline

After parsing, **show the user what you found** and ask them to confirm before
proceeding. Format it as a clean list:

"Here's what I extracted from the scheduling order:
- Trial Date: September 15, 2026
- Discovery Cutoff: July 28, 2026
- Dispositive Motion Deadline: June 15, 2026
[etc.]

Does this look right? Anything I missed or got wrong?"

This confirmation step is important because PDF parsing can miss dates or
misinterpret them, and an error here cascades through every computed deadline.

---

## Step 3: Verify Rules Are Current

Before computing deadlines, verify that the built-in rules haven't changed.
This is especially important for Colorado (the primary built-in jurisdiction).

**Verification procedure:**
1. Search the web for recent amendments to the applicable rules:
   - For Colorado: search "Colorado Rules of Civil Procedure amendments [current year]"
     and "CRCP rule changes [current year]" on coloradojudicial.gov
   - For Federal: search "Federal Rules of Civil Procedure amendments [current year]"
   - For AAA: search "AAA arbitration rules update [current year]"
   - For JAMS: search "JAMS arbitration rules update [current year]"

2. Compare what you find against the reference files:
   - Colorado: `references/colorado-crcp.md`
   - Federal: `references/federal-frcp.md`
   - Arbitration: `references/arbitration-rules.md`

3. If you find a discrepancy:
   - Tell the user: "I found that [rule X] was amended on [date]. The previous
     version said [old rule]; the current version says [new rule]. I'll use the
     updated rule for this calculation."
   - Use the corrected rule for computation.

4. If you cannot verify (e.g., search fails):
   - Tell the user: "I wasn't able to verify whether the [jurisdiction] rules
     have been updated recently. The built-in rules are current as of early 2026.
     You may want to independently confirm the key time periods."

**For non-built-in jurisdictions** (not Colorado, not Federal):
Search for the specific state's rules of civil procedure, focusing on:
- Time computation rules (equivalent of Rule 6)
- Discovery response deadlines
- Expert disclosure deadlines
- Summary judgment timelines
- Legal holidays

Present what you find to the user for confirmation before computing.

---

## Step 4: Compute Deadlines

Create the input JSON file for the computation script. The format is:

```json
{
    "matter_name": "Smith v. Jones Co.",
    "proceeding_type": "litigation",
    "jurisdiction": "colorado",
    "forum": "",
    "service_method": "electronic",
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
            "Motions in Limine": "2026-08-01",
            "Proposed Jury Instructions": "2026-08-01"
        }
    },
    "attendees": ["jane@company.com", "bob@lawfirm.com"]
}
```

Use `null` for any dates not present in the scheduling order. The script will
compute them from the rules where applicable (e.g., expert deadlines computed
backward from trial date).

Add any dates from the scheduling order that don't fit standard fields into
`custom_dates` with a descriptive label.

Run the computation:
```bash
python scripts/compute_deadlines.py --input /tmp/input.json --output /tmp/computed.json
```

Review the output and sanity-check the computed dates:
- Do all dates fall on business days?
- Are the backward-computed dates BEFORE their anchor deadlines?
- Do expert disclosure deadlines fall in a reasonable sequence?
- For arbitration: are you using arbitration rules, not litigation rules?

---

## Step 5: Generate the .ics File

Run the calendar generation:
```bash
python scripts/generate_ics.py --input /tmp/computed.json --output /path/to/output/[matter_name]_deadlines.ics
```

The output file should go to the user's workspace folder with a descriptive
filename based on the matter name.

**Before delivering the file, show the user a summary:**

"Here are the deadlines I've computed for [Matter Name]:

[List each deadline with date, description, and rule basis]

**Critical deadlines** (marked with !!!) need special attention.

The .ics file includes reminders at 7 days and 1 day before each deadline.
[If attendees were specified:] Calendar invitations will be sent to [names]
when you import the file.

**Important:** These deadlines are computed from the scheduling order and
applicable rules. They should be independently verified by counsel, especially
regarding local rules and any subsequent orders that may modify deadlines."

Then provide the .ics file link.

---

## Reference Files

Read these reference files for the detailed rules used in computation:

- **Colorado CRCP rules**: `references/colorado-crcp.md`
  - Read when jurisdiction is Colorado
  - Covers Rule 6 (time computation), Rules 26/33/34/36 (discovery), Rule 56 (summary judgment)

- **Federal FRCP rules**: `references/federal-frcp.md`
  - Read when jurisdiction is Federal
  - Key difference: FRCP counts all days for all periods; adds 3 days for e-service

- **Arbitration rules**: `references/arbitration-rules.md`
  - Read when proceeding type is arbitration
  - Covers AAA Commercial, AAA Employment, JAMS Comprehensive, JAMS Streamlined
  - Critical: Do NOT apply litigation time-computation rules to arbitration

---

## Calendar Entry Format

All calendar entries follow this format:
**[Matter Name] — [Deadline Description]**

Examples:
- Smith v. Jones Co. — Trial Date
- Smith v. Jones Co. — Last Day to Serve Interrogatories
- Smith v. Jones Co. — Plaintiff Expert Disclosure Deadline
- Smith v. Jones Co. — Arbitration Hearing

The matter name always comes first so that entries from different cases are
visually distinguishable in a crowded calendar.

---

## Edge Cases and Warnings

**Scheduling order supersedes default rules:**
If the scheduling order sets a deadline that differs from what the rules would
produce (e.g., a shorter discovery period), always use the scheduling order date.
Only use rule-based computation for deadlines NOT specified in the order.

**Arbitration is not litigation:**
If the user says "arbitration," never apply CRCP or FRCP time-computation rules.
Arbitration deadlines come from the arbitrator's order and the forum rules. If
the arbitrator's order incorporates any litigation rules by reference, note that
to the user but still apply them as the arbitrator specified.

**Local rules:**
For federal cases, local rules can significantly alter deadlines (especially
for summary judgment responses and pretrial procedures). Flag this to the user:
"Federal courts often have local rules that modify these default deadlines.
Check the local rules for [district] to verify."

**Amended scheduling orders:**
If the user mentions that the scheduling order has been amended, ask for the
most recent version. Earlier versions may have superseded dates.

**Already-passed deadlines:**
If any computed deadline falls before today's date, flag it prominently:
"WARNING: [Deadline] computed as [date], which has already passed. Verify
this is correct or whether an extension was granted."
