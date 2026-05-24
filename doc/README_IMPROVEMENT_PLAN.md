# README.md Improvement Plan

**Goal:** Maximize first impression for first-time visitors — from "What is this?" to "I want to try it" in under 30 seconds.

---

## Current State Analysis

### What the first-time visitor sees today

```
1. Title + logo
2. Subtitle "AWS CloudTrail Log Threat Hunting Tool" (dry)
3. Tagline (SIEM-equivalent …) ← jargon-heavy
4. Badges
5. One-liner + features bullets
6. Screenshots (no context captions)
7. Prerequisites table
8. Quick Start
9. Corporate Proxy section ← interrupts the flow
10. Modules table (developer-facing)
11. Architecture diagram (developer-facing)
12. Sequence Diagram link
13. Built-in Query Reference
14. License / Acknowledgements
```

### Problems identified

| # | Problem | Impact |
|---|---------|--------|
| P-1 | No "Who is this for?" statement | Visitor can't self-qualify in 5 sec |
| P-2 | Tagline starts with "SIEM-equivalent" — jargon before value | Loses non-SIEM audience immediately |
| P-3 | Features list reads as a spec sheet, not a pain-point solver | Emotional engagement is low |
| P-4 | Screenshots have no explanatory captions | Visitor doesn't understand what they're looking at |
| P-5 | No "What can I actually find?" showcase | No concrete "aha moment" before Quick Start |
| P-6 | No comparison with alternatives (Athena, CloudTrail Lake, SIEM) | Visitor doesn't understand the differentiation |
| P-7 | Corporate Proxy section sits between Quick Start and Modules | Interrupts the user journey for 95% of visitors |
| P-8 | Modules + Architecture appear before Built-in Query Reference | Developer internals have higher priority than use cases |
| P-9 | Quick Start has no "success criteria" — what should I see? | Visitors abandon if they don't know if it worked |
| P-10 | "Built-in Query Reference" is buried at the bottom | The 84 hunts are a key selling point, not an appendix |

---

## Proposed Structure

```
1.  Title + logo
2.  Hero tagline (rewritten — pain-first)
3.  Badges + key stats badges (84 hunts · 50 charts · Docker only)
4.  "Who is this for?" (3-line target audience)
5.  "Why THuntCloud?" (pain-point-first features list)
6.  Screenshots (with context captions → what do I see & why does it matter)
7.  Use Case Highlights (3 concrete scenarios)
8.  Quick Start (unchanged structure, add success criteria)
9.  Built-in Query Reference  ← moved up from bottom
10. (Optional) GeoIP setup
11. Modules table
12. Architecture diagram
13. Corporate Proxy / Troubleshooting  ← moved down
14. License / Acknowledgements
```

---

## Detailed Improvements

---

### [P-1 + P-2] Hero Tagline Rewrite

**Current:**
```
## AWS CloudTrail Log Threat Hunting Tool
> SIEM-equivalent AWS CloudTrail threat hunting on a single ordinary laptop — no cloud infrastructure required.
```

**Proposed:**
```
## Hunt AWS threats in minutes — no SIEM required
> Drop in your CloudTrail logs and get 84 ready-to-run threat hunts, a BI dashboard, and AI-assisted analysis
> — all on your laptop with a single `docker compose up`.
```

**Why:** Opens with the user's outcome ("hunt threats in minutes"), then ties to the zero-infrastructure benefit.

---

### [P-1] Target Audience Section (new)

Add a brief "Designed for" section immediately after the tagline:

```markdown
**Designed for:**
- 🔍 **Security engineers & incident responders** — investigating AWS account compromise, privilege escalation, or data exfiltration
- 🛡 **Cloud security teams** — running periodic cloud posture reviews without a dedicated SIEM
- 🧑‍💻 **Developers & SREs** — quickly auditing their own account's CloudTrail history during or after an incident
```

**Why:** Visitors self-qualify within 10 seconds. Those who see themselves in the list continue reading.

---

### [P-3] Features List — Pain-Point Rewrite

**Current (spec-sheet style):**
```
- **No-query hunting** — select a built-in hunt from the Streamlit dropdown…
- **GeoIP enrichment** — country, city, and ASN…
- **Built-in BI dashboard** — Apache Superset with pre-built CloudTrail charts
```

**Proposed (pain-first style):**
```
| | Before THuntCloud | With THuntCloud |
|---|---|---|
| 🔎 Finding threats | Write SQL or buy a SIEM | 84 built-in hunts — click and run, no SQL needed |
| 🌍 IP attribution | Manual whois lookups | GeoIP enriched automatically (country / city / ASN) |
| 📊 Visualisation | Export to Excel | 50 pre-built Superset charts ready on first launch |
| 🤖 Analysis | Read raw JSON | AI surfaces key findings in plain language |
| 💻 Infrastructure | Cloud SIEM subscription | Your laptop + Docker — zero cloud cost |
```

**Why:** The "Before / With" table immediately shows the transformation the tool provides.

---

### [P-4] Screenshot Captions — Add Context

**Current:**
```markdown
### Built-in Queries and AI Chat (Streamlit UI)
<img …>
```

**Proposed:**
```markdown
### 🔍 84 Built-in Hunts + AI Chat (no SQL, no API key needed for pre-built queries)
> Select a hunt category → click Run → results appear instantly.
> Optionally describe your investigation in plain language and the AI writes the SQL for you.
<img …>

### 📊 50 Pre-built Dashboard Charts (Apache Superset)
> Full BI dashboard with time series, heatmaps, and GeoIP world map — auto-populated from your logs.
<img …>

### 🗺 AWS Config Resource Graph
> Interactive graph showing VPC → Subnet → EC2/RDS/SG relationships from AWS Config snapshots.
<img …>
```

**Why:** Captions answer "what am I looking at and why should I run this".

---

### [P-5] Use Case Highlights (new section)

Add a "Common Use Cases" section before Quick Start with 3 concrete scenarios:

```markdown
## Common Use Cases

| Scenario | Relevant Hunts | Time to Answer |
|----------|---------------|---------------|
| 🚨 **Suspicious login alert** — unknown IP logged into the console | Console Logins · Console Login without MFA · Unusual Country Access · Impossible Travel | < 2 min |
| 🔑 **Privilege escalation investigation** — did someone expand their own permissions? | Privilege Escalation (IAM) · User Added to Admin Group · IAM Role Trust Policy Changes · IAM Permission Boundary Changes | < 3 min |
| 💥 **Post-incident sweep** — what did the attacker touch? | Root Account Activity · AssumeRole Cross-Account · CloudTrail Tampering · Defense Evasion Events · High-Risk API Monitor | < 5 min |
```

**Why:** Concrete scenarios are the fastest way to make a tool feel useful before setup.

---

### [P-6] "Why not Athena / CloudTrail Lake / SIEM?" Comparison (new section)

Add a minimal comparison block:

```markdown
## Comparison with Alternatives

| | THuntCloud | CloudTrail Lake + Athena | Commercial SIEM |
|---|---|---|---|
| Setup | `docker compose up` | S3 bucket + query config | Weeks of onboarding |
| Cost | Free (your hardware) | Per-query AWS charges | $$$ subscription |
| Offline / airgap | ✅ | ❌ | ❌ |
| Pre-built hunts | 84 out of the box | Write your own | Vendor-dependent |
| AI analysis | ✅ (optional) | ❌ | Vendor-dependent |
| Resource graph | ✅ (AWS Config) | ❌ | Limited |
```

**Why:** Eliminates the "why not just use X" objection before it forms.

---

### [P-9] Quick Start — Add Success Criteria

After Step 3, add:

```markdown
**✅ You're up and running when you see:**
- http://localhost:8501 shows a sidebar with hunt categories and a query panel
- http://localhost:8088 shows a Superset dashboard with CloudTrail charts populated
```

**Why:** Visitors need a clear "done" state. Without it, any unexpected visual triggers abandonment.

---

### [P-7] Move "Corporate Proxy" to Troubleshooting

Rename the section and move it to the bottom, just before License:

```markdown
## Troubleshooting & Advanced Setup

### Corporate Proxy / Custom CA Certificate
…existing content…

### Re-ingesting from scratch
…existing content from AGENTS.md…
```

**Why:** Only 5% of users need this. It currently sits in the middle of the first-time user journey.

---

### [P-8] Promote Built-in Query Reference

Move the "Built-in Query & Dashboard Reference" section to appear **before** the Modules/Architecture sections. Suggested order:

```
Quick Start → Use Cases → Built-in Query Reference → Modules → Architecture → Troubleshooting
```

**Why:** What the tool can *do* (hunts + charts) is more compelling to a first-time visitor than how it is architected internally.

---

## Key Stats Badges (new)

Add prominently after the existing badges row:

```markdown
![Hunts](https://img.shields.io/badge/built--in%20hunts-84-brightgreen)
![Charts](https://img.shields.io/badge/dashboard%20charts-50-blue)
![No SIEM](https://img.shields.io/badge/SIEM-not%20required-lightgrey)
```

**Why:** Numbers ("84 built-in hunts") signal depth and completeness at a glance.

---

## Priority Order for Implementation

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 High | Hero tagline rewrite [P-2] | Low | High |
| 🔴 High | "Who is this for?" section [P-1] | Low | High |
| 🔴 High | Screenshot captions [P-4] | Low | High |
| 🔴 High | Key stats badges | Low | Medium |
| 🟡 Medium | Pain-point features table [P-3] | Medium | High |
| 🟡 Medium | Use Case Highlights section [P-5] | Medium | High |
| 🟡 Medium | Quick Start success criteria [P-9] | Low | Medium |
| 🟡 Medium | Move Built-in Query Reference up [P-8] | Low | Medium |
| 🟢 Low | Comparison with alternatives [P-6] | Medium | Medium |
| 🟢 Low | Move Corporate Proxy down [P-7] | Low | Low |

---

## Notes

- All improvements must keep the existing content — this is an **addition and reordering** plan, not a rewrite.
- Screenshots (`doc/img1.png`, `doc/img2.png`, `doc/img3.png`) exist and just need better captions — no new images required.
- The "Before / With" features table and "Use Case Highlights" table are the two changes most likely to convert a first-time visitor into a user.

