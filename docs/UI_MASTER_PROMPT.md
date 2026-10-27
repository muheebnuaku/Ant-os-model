# ANT-OS Ω — Interface Master Prompt

> Use this document as the complete brief for designing or building any screen of
> the ANT-OS Ω / AFRICA-OS Ω web application. Follow it literally. Where it is
> silent, choose the more restrained, more ordered option.

---

## 1. What you are designing

ANT-OS Ω is a sovereign, validation-first decision-intelligence system for
African public institutions. AFRICA-OS Ω is the policy profile it runs (the
24-Hour Africa Economy Policy, Ubuntu, inclusion, AfCFTA). It receives evidence
("signals") from ministries, agencies, markets and communities. It checks that
evidence, scores how far it can be trusted, advises an action, calls a human
when it must, and keeps a permanent, tamper-evident record of everything.

**Who uses it:**
- Ministry directors and sector leads, who decide and approve.
- Analysts, who run and read decisions.
- Field operators, who submit evidence.
- Regulators, who audit and override.
- Administrators and the sovereign authority, who set the rules.

Most are senior, busy, non-technical people working under pressure.

**What the interface must feel like:** a serious instrument of government. It
should be ordered, calm, precise and trustworthy, like a well-run cabinet
office: everything in its place, the most important thing first, nothing
decorative. It must never feel like a tech demo, a game or a chatbot.

**Creator attribution (required on every page footer):** "ANT-OS Ω / AFRICA-OS Ω,
the VPF and the 24-Hour Africa Economy Policy are the work of Dr. David King Boison."

---

## 2. Governing principles (in priority order)

1. **Hierarchy before decoration.** Every screen has one clear reading order:
   status → what needs action → supporting detail → raw record. The eye should
   never have to search.
2. **One structure everywhere.** Every page uses the same frame and the same page
   template (§4). Users learn it once.
3. **Evidence over assertion.** Every number, status and sentence on screen comes
   from stored data. Nothing is estimated, decorated or invented. A sector with no
   data says "No data", never a placeholder number.
4. **Plain language.** Write for a minister, not an engineer. Technical detail
   (hashes, IDs, JSON) is available, but always one level down, never on the
   first view.
5. **Restraint.** Few colors, one accent, one primary action per page, generous
   but consistent spacing. If an element doesn't help a decision, remove it.
6. **Status is sacred.** Status colors mean status and nothing else, and always
   come with an icon and a text label.

---

## 3. Prohibited

- Sparkle, star, magic-wand, robot, brain or "AI" icons and imagery of any kind.
- Neon colors, glows, light trails, gradients used as decoration, animated or
  ambient backgrounds, grid-paper "hacker" textures, glassmorphism and heavy blur.
- Emoji anywhere in the interface.
- "Magic" or hype language ("AI-powered", "smart", "insights at your fingertips").
  The system "advises" and "checks"; it does not "think".
- Floating, overlapping or free-positioned layouts. Everything sits on the grid.
- More than one primary (filled) button visible in a page section.
- Decorative charts, 3D charts, pie charts with more than 5 slices, dual-axis
  charts, and a number printed on every data point.
- Color as the only carrier of meaning.
- Centered body text (except empty states), ALL-CAPS paragraphs, and italic UI text.
- Tooltips as the only way to reach information.

---

## 4. The application frame and page template

### 4.1 Frame (identical on every signed-in page)

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│              │ HEADER BAR (64 px, fixed)                               │
│  SIDEBAR     │ Breadcrumb ............. Search ▢  Node status  User ▾  │
│  (248 px,    ├──────────────────────────────────────────────────────────┤
│   fixed)     │ CONTENT AREA (max width 1440 px, 32 px side padding)     │
│              │   Page template (§4.2)                                   │
│  Logo        │                                                          │
│  Nation      │                                                          │
│  Nav groups  │                                                          │
│              │                                                          │
│  ─────────   │                                                          │
│  Help        │ Footer: attribution · version · node id                  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Sidebar** (solid surface, 1 px right border, no shadow):
1. Product mark "ANT-OS Ω" (wordmark only, no illustration). Below it the
   nation in small text, e.g. "Ghana · AFRICA-OS Ω".
2. Navigation in labeled groups, in this exact order. Show only items the
   user's role allows.
   - **Overview:** Briefing
   - **Operations:** Review queue (with a count badge of items assigned to the
     user), Decisions, New decision
   - **Evidence:** Signals
   - **Assurance:** Records & verification
   - **Administration:** Rules & configuration, Access & keys
3. Bottom: Help, then the signed-in user's name and role.

Nav items have a 20 px icon and a label, 40 px tall. The active item gets a
tinted background, a 3 px accent bar on the left and semibold text. The sidebar
collapses to icons only below 1200 px. Below 768 px it becomes a menu button.

**Header bar** (solid surface, 1 px bottom border):
- Left: breadcrumb (e.g. "Decisions / Plan oxygen supply…").
- Center-right: global search ("Search decisions, sectors, records…", Ctrl+K).
  It opens a command menu with grouped results: Pages, Sectors, Decisions,
  Actions.
- Right: **node status** as a compact text indicator ("Records verified ·
  sealed 2 h ago", shield icon, status color), then the user menu (name,
  roles, appearance, sign out).

### 4.2 Page template (every page, top to bottom, no exceptions)

| # | Zone | Content | Rules |
|---|------|---------|-------|
| 1 | **Page header** | Title (H1), one-line description, the page's single primary action on the right | Title is a noun ("Review queue"), not a sentence |
| 2 | **Context bar** | Filters and scope controls: time window, sector, status, search | One row, left-aligned. It controls everything below it. Never repeat filters inside cards |
| 3 | **Summary strip** | 3–5 key figures (KPI tiles) of equal width | Each tile: label, value, one comparison or status line. No charts larger than a sparkline |
| 4 | **Primary section** | The thing the user came to do (a queue, a table, a verdict) | Full width or 8 of 12 columns |
| 5 | **Secondary section** | Supporting context | 4 of 12 columns beside the primary section, or full width below it |
| 6 | **Detail section** | Breakdowns, history, technical record | Collapsed or lower on the page. Raw JSON only inside a "Technical record" disclosure |

Sections are separated by 32 px. Every section has a header row: title (H2,
left), optional short description (muted, below the title), and optional
secondary actions (right, text buttons). Never stack two cards without a
section header explaining them.

### 4.3 Grid and spacing

- 12-column grid, 24 px gutters, content max width 1440 px.
- Spacing scale (use only these values): 4, 8, 12, 16, 24, 32, 48 px.
- Card padding: 24 px. Table cell padding: 12 px vertical, 16 px horizontal.
- Align everything to the grid's left edge. Numbers in tables align right.

---

## 5. Visual system

### 5.1 Typography

One family: the system sans (`system-ui, -apple-system, "Segoe UI", Roboto,
"Noto Sans", sans-serif`). No display or serif faces. Monospace only inside
the technical record.

| Role | Size / line height | Weight | Use |
|------|------|--------|-----|
| H1 page title | 28 / 36 | 600 | One per page |
| H2 section title | 18 / 26 | 600 | Section headers |
| H3 card title | 15 / 22 | 600 | Card and panel titles |
| Body | 14 / 22 | 400 | Default text |
| Small | 13 / 20 | 400 | Secondary text, table text |
| Caption | 12 / 16 | 500 | Labels, metadata, axis text |
| KPI value | 32 / 38 | 600 | Summary strip figures (proportional digits) |
| Verdict | 22 / 30 | 600 | The single advised action on a decision page |

Use sentence case everywhere. Use tabular figures only in table columns.

### 5.2 Color

Light theme is the default; a dark theme is offered under the user menu and
follows the device setting. Both are specified, not auto-inverted.

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| page | `#F7F7F5` | `#111111` | Page background (flat, no gradient) |
| surface | `#FFFFFF` | `#1A1A19` | Cards, sidebar, header |
| surface-subtle | `#F2F1EE` | `#222220` | Table headers, inset areas |
| border | `#E3E2DD` | `#2E2E2B` | 1 px borders and dividers |
| text | `#111111` | `#F0EFEC` | Primary text |
| text-secondary | `#52514E` | `#C3C2B7` | Descriptions |
| text-muted | `#6F6D68` | `#959389` | Metadata, captions |
| accent | `#1F5FAF` | `#3987E5` | Primary buttons, links, active nav, data series 1 |
| accent-subtle | `#E8F0FA` | `#1B2A3D` | Active nav background, selected rows |

**Status palette** (fixed, used only for status):

| Status | Color | Icon | Means |
|--------|-------|------|-------|
| Good | `#0CA30C` | check-circle | Trusted, stable, passed, resolved |
| Warning | `#FAB219` | alert-triangle | Attention, decayed, medium priority |
| Serious | `#EC835A` | shield-alert | Conflicted, high priority, escalate |
| Critical | `#D03B3B` | octagon-x | Blocked, critical, failed, overdue |
| Neutral | text-muted | circle-dashed | No data, not assessed, deferred |
| Informational | accent | info | Provisional, in progress |

Status appears as a **badge**: a tinted background, a 14 px icon in the status
color, and a dark label. Never a bare colored dot without a label, except
inside a legend.

### 5.3 Surfaces, borders, elevation

- Cards: surface color, 1 px border, 8 px radius, no shadow or the faintest one
  (`0 1px 2px rgba(0,0,0,.04)`).
- Only overlays (menus, drawers, dialogs) get a real shadow.
- Radius: 6 px for controls, 8 px for cards, 12 px for dialogs and drawers.
- No blur, no transparency on surfaces, no gradients.

### 5.4 Icons

- One set: Lucide, outline, 1.75 px stroke. 16 px inline, 20 px in navigation.
- Icons label functions (search, filter, download, verify, record), never
  decorate. A section title may have one leading icon; body text never does.
- **Banned:** sparkles, stars, wands, robots, brains, lightning bolts, rockets.

### 5.5 Motion

- 150–200 ms ease-out for hover, expand, drawer open and close, dialog open and
  close, and tab or segment change (the underline or thumb slides to the new
  choice). A page fades in over 150 ms. Nothing loops except a small spinner
  while waiting, and a gentle pulse on the "live" indicator.
- No page-load choreography, staggered card entrances, parallax or bouncing.
- Respect `prefers-reduced-motion` (all motion off).

---

## 6. Components

**Buttons.** Primary (filled accent, white text): one per section. Secondary
(surface, 1 px border). Tertiary (text only, accent color). Destructive
(secondary style with a critical-colored label). Height 32 px, 13 px medium
text (28 px compact variant). Label is a verb: "Resolve", "Verify decision",
"Export". Buttons show a brief press response and a spinner while busy.

**Density.** All controls, table rows and navigation items take their size
from shared tokens. The user menu offers Compact (28 px controls, 36 px rows),
Standard (32 px / 44 px, the default) and Comfortable (36 px / 52 px), applied
everywhere at once and remembered per browser.

**KPI tile.** Caption label (top), value (32 px), then one line of context
(comparison like "+3 vs previous 24 h", or a status badge). Equal widths in a
row; never more than 5.

**Tables** (the default way to show lists):
- Sticky header on a subtle background, 12 px caption-style column headers in
  sentence case.
- Rows 48 px tall; the whole row is clickable when it opens a detail.
- Leftmost column: the primary identifier in semibold, with a muted second line.
- Status is a badge column. Numbers align right. Timestamps are relative with
  the absolute time on hover.
- Pagination or "Load older" at the bottom. Empty, loading (skeleton rows) and
  error states are all designed.

**Filters.** Segmented control for 2–4 exclusive options, select for longer
lists, search input with an icon. All filters sit in the context bar (§4.2,
zone 2).

**Tabs.** Use them on detail pages to separate Overview / Evidence / Checks /
Record. Underline style, never pills.

**Drawer.** Right side, 560 px, for quick detail without leaving the list:
sector detail, record detail. It has a header (title, status, close), then
sections in the same order as a page.

**Dialogs.** Only for confirmations and short required inputs (e.g. the
resolution note). Title, one sentence, the field, then right-aligned actions
(secondary, then primary).

**Empty state.** Muted icon, one-line title, one-line explanation, and an
optional action. Centered within its section.

**Notices.** Full-width bar inside the section it concerns: status icon, one
sentence, and an optional link. Used for verdicts, verification results and
errors.

**Charts.** See §8.

---

## 7. Screens: exact content and order

### 7.1 Briefing (home)
1. **Page header:** "Briefing" · "National picture for Ghana" · primary action
   "New decision".
2. **Context bar:** time window (6 h / 24 h / 3 days / 7 days) · last updated
   time · live indicator.
3. **Summary strip** (4 tiles):
   - Waiting for review (with the number due within 30 min);
   - Overdue reviews;
   - Decisions in the window (with the change against the previous window);
   - Cleared to act (%).
4. **Situation summary:** a notice-style panel with up to 3 plain sentences,
   generated by rules from the data. For example: "Finance has a critical
   review due in 12 minutes." / "Data from Education has not arrived in 24 hours."
5. **Primary (8 columns): "Needs action".** A table of open reviews sorted by
   deadline. Columns: priority, decision, sector, assigned to, time remaining
   (with a progress bar), action ("Open").
6. **Secondary (4 columns): "Sector status".** All eight sectors in a fixed
   order (health, agriculture, finance, energy, transport, education,
   governance, ports). Each row shows a status badge, data freshness and the
   number of open reviews.
7. **Detail (full width): "Activity by sector".** A heatmap of sectors × time
   buckets, colored by the weakest validation result in each cell, with a
   legend and a "View as table" toggle.
8. Selecting a sector anywhere opens the **Sector drawer**:
   - status;
   - key figures;
   - latest readings (table: signal, source, observed, freshness);
   - open reviews;
   - recent decisions.

### 7.2 Review queue
1. **Page header:** "Review queue" · "Decisions waiting for a person".
2. **Context bar:** status tabs (New · In progress · Resolved · All) · sector ·
   priority · "Assigned to me / All" (regulators only).
3. **Summary strip:** New · In progress · Due within 30 min · Overdue.
4. **Primary: table.** Columns: priority, decision and reasons, sector,
   assigned role, deadline (remaining time and bar), status, actions
   ("Acknowledge", "Resolve…").
5. "Resolve…" opens a dialog that requires a resolution note ("This note
   becomes part of the permanent record").

### 7.3 Decisions
1. **Page header:** "Decisions" · "Every decision ANT-OS has evaluated" ·
   primary action "New decision".
2. **Context bar:** search · sector · result (Trusted / Provisional /
   Conflicted / Blocked / Decayed) · outcome (Cleared to act / Needs a person /
   On hold) · date range.
3. **Summary strip:** Total in range · Cleared to act · Needs a person · Blocked.
4. **Primary: table.** Columns: decision (objective plus sector), evidence
   result badge, confidence (number and thin bar), advised action badge, human
   review (yes/no), evaluated at.

### 7.4 Decision detail
Breadcrumb: Decisions / {objective}.
1. **Page header:** the objective as the title · sector, nation and time as the
   description · secondary actions "Verify decision" and "Export".
2. **Verdict panel** (full width, the most prominent element on the page). Left:
   - "ANT-OS advises" + action badge (verdict size);
   - the primary recommendation in one or two sentences;
   - a notice: "Cleared to act" / "A person must review this before anyone
     acts" / "Not enough trustworthy evidence to act".

   Right:
   - confidence (KPI style) and the evidence result badge;
   - "Advice written by: rules / model name (checked by rules)".
3. **Tabs:**
   - **Overview** (default):
     - (a) "Why", with the secondary recommendations, then two labeled
       paragraphs, "Effect on people (Ubuntu)" and "Effect on the 24-hour
       economy";
     - (b) "Checks", a 5-row table (Sources agree, Inclusion, 24-hour economy,
       Environment, Local fit), each with a result badge (Passed / Concern /
       Failed / Not assessed) and a one-line finding;
     - (c) "Safeguards applied", a list of plain sentences;
     - (d) "Human review", if any: priority, assigned role, deadline, reasons,
       and a link to the queue.
   - **Evidence:** the signals used (table: type, reading, source, kind of
     source, observed, freshness, reliability), then contradictions found.
   - **Confidence:** the breakdown chart (§8) and its table.
   - **Record:**
     - the 19-step trail as an ordered list in five labeled groups (Gathering
       evidence 1–6, Weighing 7–9, Doctrine checks 10–13, Advice 14,
       Safeguards and record 15–19), each step expandable to its finding;
     - the verification result;
     - "Technical record" (IDs, hashes, raw JSON, the exact model response) in
       a collapsed disclosure.

### 7.5 New decision
A single-column form, max width 880 px, in three numbered sections:
1. **Decision:** sector, objective, "serious consequences" checkbox.
2. **Evidence:** repeatable evidence rows (what it measures, reading, reported
   by, kind of source, observed at, reference), "Add evidence from another
   source", and a help line: "Two independent sources that agree are far more
   trustworthy than one."
3. **Context (optional):** 24-hour economy and local-fit questions, each a
   three-way control (Unknown / Yes / No). Unknown is the default and is never
   treated as yes or no.

Sticky footer bar: "Cancel" (secondary) and "Evaluate decision" (primary).
Validation messages appear inline under their fields.

### 7.6 Records & verification
1. **Page header:** "Records & verification" · "The permanent, tamper-evident
   record of every action" · primary action "Verify all records".
2. **Integrity panel** (full width): a status notice ("All 1,284 records
   intact · 32 seals valid" or a precise failure statement). Beside it: last
   verified, last sealed, records since the last seal.
3. **Summary strip:** Records · Seals · Decisions replayed (matched / total) ·
   Last seal.
4. **Secondary actions row:** "Re-run every decision", "Seal records now"
   (each with a one-line explanation).
5. **Primary: history table.** Columns: event (plain name), reference, by
   whom, when, open. Filter by event type in the context bar.
6. Selecting a row opens a drawer: plain summary first; fingerprint, previous
   link and raw content in the technical record section.

### 7.7 Signals (evidence)
Header, context bar (sector, signal type, source, time), summary strip
(received, sources, mean freshness, stale), then a table of signals (type,
reading, source, kind, observed, received, freshness).

### 7.8 Sign in
A centered card (max 420 px) on the flat page background:
1. The wordmark;
2. "Sign in";
3. the access-key field;
4. the primary button;
5. a one-line privacy note.

No illustration, no marketing copy. Single sign-on button above the key field
once Keycloak is enabled.

---

## 8. Charts

- Use charts only where change over time or a breakdown matters: the activity
  heatmap, KPI sparklines, the confidence breakdown, and freshness bars. Show
  everything else as a number or a table.
- Thin marks: 2 px lines, 4 px rounded bar ends, hairline gridlines and axes,
  muted 12 px axis text.
- One accent hue for single series. Status colors only for status encodings.
  Positive and negative contributions use accent vs `#E34948` (light) /
  `#E66767` (dark).
- Every chart with more than one color has a legend. Every chart has a hover
  and keyboard-focus tooltip, and a "View as table" equivalent.
- Never a dual-axis chart, never 3D, never a number on every mark.

---

## 9. Language

- **Voice:** a capable civil servant. Short, factual, specific. "Finance has a
  critical review due in 12 minutes." Not "Heads up! Finance needs some love."
- **Terminology:** "Decision", "evidence" (in the UI) for signals, "review"
  for escalation, "record" for audit entry, "seal" for anchor, "cleared to act"
  for allowed-for-action. Translate system codes into sentences; never show
  `snake_case`.
- **Dates:** relative for recent ("12 min ago"), absolute on hover and in
  records ("25 Oct 2026, 14:05 GMT"). Times in the user's time zone, labeled.
- **Numbers:** percentages without decimals in summaries, one decimal in
  detail. Thousands separators.
- "Not assessed" and "No data" are always written out; never blank, zero or a dash alone.

---

## 10. Accessibility and responsiveness

- WCAG 2.2 AA: 4.5:1 text contrast, visible 2 px focus rings, full keyboard
  operation, correct landmarks and headings (one H1 per page), labelled
  controls, and live regions for updates.
- Status is always conveyed through text and an icon, never color alone.
- Breakpoints:
  - ≥ 1440: full layout;
  - 1200–1439: sidebar remains;
  - 768–1199: sidebar collapses to icons, secondary columns drop below the
    primary;
  - < 768: single column, sidebar behind a menu button, tables become stacked
    rows.

---

## 11. Acceptance checklist (every screen must pass)

- [ ] Uses the frame (§4.1) and the page template zones in order (§4.2).
- [ ] Exactly one H1 and at most one primary button per section.
- [ ] All spacing values come from the scale; everything aligns to the grid.
- [ ] Every status shows icon + label; status colors are used only for status.
- [ ] No banned icons, effects or language (§3).
- [ ] Every figure traces to stored data; empty data reads "No data".
- [ ] Technical detail is one level down, inside "Technical record".
- [ ] Loading, empty and error states exist for every data region.
- [ ] Works by keyboard; passes contrast; respects reduced motion.
- [ ] Footer carries the creator attribution.
