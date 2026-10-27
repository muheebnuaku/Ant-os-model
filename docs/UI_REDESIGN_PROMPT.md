# ANT-OS Ω — Interface Redesign Prompt (v2: "sleek and ordered")

> Use this brief to redesign the ANT-OS Ω web application. It **keeps** the
> structure, order and rules of `docs/UI_MASTER_PROMPT.md` (frame, page template,
> screen contents, honesty rules) and **replaces** its visual layer with a more
> refined one. Where the two documents conflict, this one wins on look and feel;
> the master prompt wins on structure, content and data honesty.
>
> Target quality: a professional, government-grade operations product with the
> finish of the best modern work tools. It is precise, quiet and confident, with
> a consistent rhythm. It is never playful, techy or decorative.

---

## 1. Context (unchanged)

ANT-OS Ω is a sovereign, validation-first decision-intelligence system for
African public institutions, running the AFRICA-OS Ω policy profile (24-Hour
Africa Economy Policy, Ubuntu, inclusion, AfCFTA).

- **What it does:** it checks evidence, scores how far it can be trusted,
  advises an action, calls a human when it must, and keeps a tamper-evident
  record of everything.
- **Who uses it:** ministry directors, sector leads, analysts, field operators,
  regulators and the sovereign authority. They are busy, senior and mostly
  non-technical.
- **Footer attribution, required on every page:** "ANT-OS Ω / AFRICA-OS Ω, the
  VPF and the 24-Hour Africa Economy Policy are the work of Dr. David King
  Boison."

## 2. What "sleek" means here

1. **Calm surfaces, sharp details.** Large quiet areas; precision at the edges
   (hairline borders, aligned baselines, exact numbers).
2. **Typography does the hierarchy.** Size, weight and colour separate levels,
   not boxes, lines and colour blocks.
3. **Fewer containers.** Section titles sit outside cards. Cards only group
   things that belong together. Never nest a card inside a card.
4. **One rhythm.** Every gap comes from the spacing scale, and repeated items
   line up to the pixel.
5. **Numbers are first-class.** Tabular figures, consistent units, right
   alignment, and a muted unit next to a strong value.
6. **Motion confirms, never performs.** Every transition answers "what just
   changed?"

## 3. Still prohibited (from the master prompt, plus additions)

- Sparkle, star, wand, robot, brain, rocket or lightning icons; "AI-powered"
  language; emoji.
- Neon, glows, decorative gradients, glassmorphism, blur, animated backgrounds,
  grid-paper textures.
- Floating or overlapping layouts; more than one primary button per section.
- Heavy shadows, thick borders, ALL-CAPS labels longer than two words, coloured
  section backgrounds.
- **New:** pill-shaped buttons, oversized radii (> 12 px), icon + text pairs
  where the text alone is clear, and centred page titles.

## 4. Foundations

### 4.1 Typeface

- **Inter** (variable), loaded with `next/font` and self-hosted. Fallback:
  `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Enable `font-feature-settings: "cv11", "ss01"` (clean single-storey forms)
  globally, and `"tnum"` on numeric columns, KPI values and timestamps.
- Use **JetBrains Mono** (or `ui-monospace`) only inside the "Technical record".

| Role | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|
| Display (page title) | 24 / 32 | 600 | −0.02em | One per page |
| Section title | 15 / 22 | 600 | −0.01em | Section headers (outside cards) |
| Card title | 14 / 20 | 600 | −0.005em | Inside cards |
| Body | 14 / 22 | 400 | 0 | Default |
| Secondary | 13 / 20 | 400 | 0 | Descriptions, table text |
| Label | 12 / 16 | 500 | +0.01em | Field labels, column headers, KPI labels |
| Micro | 11 / 14 | 500 | +0.02em | Metadata, axis ticks (sparingly) |
| KPI value | 28 / 34 | 600 | −0.02em | Tabular figures |
| Verdict | 20 / 28 | 600 | −0.01em | The advised action |

Use sentence case everywhere. Colour separates primary, secondary and muted
text; weight is reserved for titles and values.

### 4.2 Colour

A cool, neutral base with one confident accent. Light is the default; dark is a
first-class, separately tuned theme.

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#FAFAFA` | `#0A0A0B` | Page |
| `surface` | `#FFFFFF` | `#111113` | Cards, sidebar, header |
| `surface-2` | `#F4F4F5` | `#18181B` | Table header, inset areas, hover |
| `surface-3` | `#EEEEF0` | `#1F1F23` | Pressed, selected inset |
| `border` | `#E4E4E7` | `#27272A` | Hairlines (1 px) |
| `border-strong` | `#D4D4D8` | `#3F3F46` | Inputs, hover borders |
| `text` | `#09090B` | `#FAFAFA` | Primary text, values |
| `text-2` | `#52525B` | `#A1A1AA` | Secondary text |
| `text-3` | `#71717A` | `#8B8B94` | Labels, metadata |
| `accent` | `#2457D6` | `#5B8DEF` | Primary actions, links, focus, selection |
| `accent-hover` | `#1D47B3` | `#7AA3F2` | |
| `accent-subtle` | `#EEF3FD` | `#162238` | Selected rows, active nav |

**Status** (meaning only; always icon + label):

| Status | Foreground | Light background | Dark background |
|---|---|---|---|
| Good | `#15803D` | `#ECFDF3` | `#0F2A1B` |
| Warning | `#B45309` | `#FFFBEB` | `#2D2008` |
| Serious | `#C2410C` | `#FFF4ED` | `#2F1A0E` |
| Critical | `#B91C1C` | `#FEF2F2` | `#2E1414` |
| Info | the accent | the accent-subtle | the accent-subtle |
| Neutral | `text-3` | `surface-2` | `surface-2` |

Charts keep the validated data-viz palette (series 1 `#2A78D6` light /
`#3987E5` dark; negative `#E34948` / `#E66767`). Their status colours are the
status foregrounds above. Run the palette validator after any change.

### 4.3 Space, shape, depth

- **Spacing scale:** 4, 8, 12, 16, 20, 24, 32, 40, 56.
  - Page gutter: 32 (16 on mobile).
  - Between sections: 40.
  - Section title to content: 12.
  - Card padding: 20.
- **Radius:**
  - 6: controls, badges.
  - 8: cards, table containers.
  - 12: drawers, dialogs, command menu.
- **Depth:** flat by default (1 px border, no shadow).
  - Hover lift on clickable cards: border goes to `border-strong`; no shadow.
  - Overlays (menus, drawers, dialogs, toasts):
    `0 1px 2px rgb(0 0 0 / .06), 0 8px 24px -4px rgb(0 0 0 / .12)` (light),
    stronger in dark.
- **Content width:** 1280 px max for data pages, 760 px for forms and Help.
  Centred in the content area.

### 4.4 Icons

- Lucide, 1.5 px stroke.
- Sizes: 16 px inline, 18 px in navigation, 14 px inside badges.
- Colour `text-3` unless it carries status.
- One icon per nav item and per section action. No decorative icons beside
  titles.

### 4.5 Motion

- **Timing:** 140–200 ms. Use `cubic-bezier(0.2, 0.7, 0.2, 1)` for movement and
  `ease-out` for fades.
- **Moments:**
  - Hover and press: 120 ms colour change; press scales to 0.98.
  - Tab and segment change: the underline or thumb slides (200 ms).
  - Drawer and dialog: enter 200 ms, exit 160 ms.
  - Page: 150 ms opacity fade.
  - Data refresh: the old content dims to 60% until the new data arrives. No
    skeleton flash.
  - Numbers that change: crossfade 150 ms. No counting animation.
- **Never:** staggered entrances, parallax, bouncing, looping decoration.
  Respect `prefers-reduced-motion`.

## 5. Components (refined)

**Buttons**:
- Shape: 32 px tall (28 compact, 36 comfortable), 6 px radius, 13 px / 500
  text, 12 px horizontal padding, 16 px icons, 6 px gap.
- Primary: accent fill, white text, 1 px inner highlight
  `inset 0 1px 0 rgb(255 255 255 / .12)`.
- Secondary: surface fill with a `border-strong` hairline.
- Ghost: no border; `surface-2` on hover.
- Destructive: secondary style with critical text.
- Behaviour: busy shows a 12 px spinner and keeps the width. Disabled is 45%
  opacity with no hover change.
- Icon-only buttons: 32 × 32 with a tooltip.

**Inputs and selects**:
- 32 px tall, 6 px radius, `border-strong` hairline, `surface` fill.
- Placeholder in `text-3`.
- Focus: accent border plus a 3 px `accent-subtle` ring.
- Labels sit above the field (12 / 500, `text-2`). Help and error text sit
  below (12, `text-3` / critical).
- Selects use a custom chevron.

**Segmented control**: `surface-2` track; the selected item is a `surface`
thumb with a hairline and a 1 px shadow, and it slides.

**Tabs**: 13 px / 500 text, 36 px tall. The active tab has `text` colour and a
2 px accent underline that slides. Tab counts show as small muted numbers.

**Badges**:
- 22 px tall, 6 px radius, 12 px / 500 text, status icon at 14 px.
- Tinted background with dark text in light mode.
- A "dot" variant (8 px dot + label) is for dense tables.

**KPI tile**:
- Label (12 / 500, `text-3`).
- Value (28 / 600, tabular), with an optional muted unit or "/ total".
- One context line holding a delta chip: ▲ or ▼, a signed number and
  "vs previous 24 h", green or red *only* when the direction is unambiguous
  good or bad, otherwise neutral.
- Optional 64 × 20 sparkline aligned to the right.
- No border between tiles: put 4 tiles in one card, divided by 1 px vertical
  hairlines.

**Tables**:
- Header: 36 px tall, `surface-2`, label style, sticky.
- Rows: 44 px tall with hairline row dividers and no vertical lines.
- Row hover is `surface-2`; a selected row is `accent-subtle` with a 2 px
  accent bar on the left.
- First column: semibold primary text with a muted second line.
- Numbers are right-aligned and tabular. Status uses the badge dot variant.
- Row actions are ghost buttons, visible on hover and always on focus.
- Footer: count ("Showing 1–50 of 312") and pagination.
- Loading: 6 skeleton rows with the column widths preserved.

**Cards**: `surface`, 1 px border, 8 px radius, 20 px padding. A card title
row is only used when the card stands alone. When it sits under a section
title, it has no inner title.

**Section header**: title (15 / 600) and an optional muted description on one
line beneath, with ghost actions right-aligned on the title's baseline.

**Notices**: 1 px border in the status colour at 30% opacity, a status-tinted
background, a 16 px icon, one sentence, and an optional inline link.

**Drawer**: 520 px, slides from the right, 12 px left radius.
- Header: eyebrow, title, status badge and close button.
- Body: the same section rhythm as a page.
- Footer: actions right-aligned and sticky.

**Dialog**: 480 px, centred, 12 px radius.
- Content: title (15 / 600), one sentence, the fields.
- Actions: right-aligned in a footer with a hairline above.

**Command menu (Ctrl K)**:
- Size and position: 640 px wide, 12 vh from the top.
- Input: 48 px.
- Results: grouped with 11 px uppercase group labels (the one allowed
  uppercase). Each item is a 36 px row with its icon, label and a muted
  hint on the right.
- Footer: key hints (↑↓ navigate, ↵ open, esc close).

**Toasts**: bottom-right, 360 px wide.
- Content: a status icon, one line and an optional "View" link.
- Behaviour: auto-dismiss after 5 s, pause on hover, slide up 8 px on enter.

**Empty states**: a 32 px muted icon in a 48 px `surface-2` circle, a title
(14 / 600), one line (13, `text-3`) and an optional secondary button.
Centred in its section.

## 6. Frame (same structure, refined finish)

**Sidebar** (240 px; 64 px when collapsed):
- Background: `surface` with a 1 px right border.
- Top: the product mark (an 8 px-radius 24 px square with "Ω" in white on
  the accent), then "ANT-OS Ω" (14 / 600) and "Ghana · AFRICA-OS Ω" (12,
  `text-3`).
- Nav groups: 11 / 500 labels in `text-3`, 20 px above each group.
- Nav items: 32 px tall with 18 px icons.
  - Hover: `surface-2`.
  - Active: `accent-subtle` background, accent icon, `text` label and a
    500 weight.
- The review queue count is a small critical badge.
- Bottom: Help, a collapse toggle, then the user card (avatar initials,
  name, role).

**Header** (56 px; `surface` at 85% over `bg`, with a 1 px bottom border):
- Left: the breadcrumb (13 px, `text-3`, current page in `text`).
- Right:
  - search trigger (280 px, `surface-2`, placeholder and a ⌘K/Ctrl K chip);
  - the records seal status (shield icon plus "Verified · sealed 2 h ago");
  - the avatar menu.

**Footer**: 12 px `text-3`, with the attribution on the left and engine,
rules and node on the right.

## 7. Screen treatments (order exactly as in the master prompt §7)

**Briefing**:
1. **Summary card:** the KPI strip as a single 4-tile card.
2. **Situation summary:** a quiet list of up to 3 sentences, each with a
   status dot. No coloured panel.
3. **Needs action** (8 columns) and **Sector status** (4 columns). The sector
   status is a compact list; each row shows the sector name, a status badge
   (dot variant), a freshness bar (48 px) and the review count. The fixed
   sector order is unchanged.
4. **Activity by sector:**
   - heatmap cells 20 px tall with 2 px gaps and 3 px radius;
   - the legend sits in the section header row, right-aligned.

**Review queue**:
- Status tabs with counts; filters in one row beneath.
- Deadline column: the remaining time over a 4 px bar. It turns critical
  when overdue.
- Resolve opens the dialog, and the note field auto-focuses.

**Decisions**: the context bar holds search, sector, result, outcome and date.
Confidence shows as a number plus a 48 px bar. Clicking a row opens the
decision page.

**Decision detail** (the showcase page):
- **Verdict panel**, full width:
  - Left: "ANT-OS advises" (12, `text-3`), the action as verdict text with
    its badge, and the recommendation (15 / 24).
  - Right: confidence (KPI style) with a 120 px bar marked at the sector's
    trusted and provisional thresholds, the evidence result badge, and who
    wrote the advice.
  - Bottom of the panel: the clearance notice.
- **Tabs:** Overview / Evidence / Confidence / Record.
  - The **Record** trail is a vertical timeline:
    - a 1 px connecting line;
    - 20 px numbered nodes;
    - the five group titles as timeline headers;
    - each step expandable inline.

**New decision**:
- A 760 px form.
- Numbered steps shown as a slim progress header (1 Decision · 2 Evidence ·
  3 Context) that highlights the section in view.
- A sticky footer bar with Cancel and "Evaluate decision".

**Records & verification**:
- Integrity hero: a large status line ("All 1,284 records intact") with the
  shield icon and three facts as a definition row.
- The "linked records" strip: the last 6 entries as connected 160 px cards
  with the event name, time and a short fingerprint in mono; sealed entries
  get a small seal mark.
- History table below.

**Signals**: a standard table page. Stale rows show a warning dot-badge on the
freshness cell.

**Sign in**:
- A 380 px card, centred on `bg`.
- Content: the mark, "Sign in to ANT-OS", the access-key field, the primary
  button and a one-line privacy note.
- Nothing else.

## 8. Responsive behaviour

| Width | Layout |
|---|---|
| ≥ 1440 | Full layout |
| 1024–1439 | 8/4 sections stack below 1200 |
| 768–1023 | Sidebar collapsed to icons; KPI card becomes 2×2 |
| < 768 | Sidebar behind a menu button; tables become stacked rows (label: value); sticky form footer stays |

Touch targets are at least 40 px on touch devices (Comfortable density applies
automatically on coarse pointers).

## 9. Accessibility (non-negotiable)

- WCAG 2.2 AA contrast for all text (check `text-3` on `surface-2`).
- A visible 2 px accent focus ring with 2 px offset on every interactive element.
- Full keyboard paths: tabs, segmented controls, tables (row focus), drawers
  and dialogs (focus trap, Esc closes, focus returns to the trigger).
- Status is always icon + text. Charts have legends and table equivalents.
- Live regions for toasts and refreshed data. One H1 per page.

## 10. Implementation notes

- Express every value above as a CSS custom property (`--bg`, `--text-2`,
  `--space-5`, `--radius-card`, `--ctl-h`, …). Components use tokens only;
  no raw hex in components.
- Keep the existing density tokens (Compact / Standard / Comfortable) and map
  the sizes in §5 onto Standard.
- Keep the existing data hooks, URL state, caching, keyboard shortcuts and
  routes; this is a visual redesign, not a rewrite of behaviour.
- One small API addition is needed: `GET /v1/sectors` should also return each
  sector's `validation_thresholds` (trusted, provisional), so the decision
  page can mark them on the confidence bar. Today only the restricted
  `/v1/admin/config` returns them.
- After the redesign, run the data-viz palette validator for both themes and
  record the results in the pull request.

## 11. Acceptance checklist

- [ ] Frame, page template and screen order match the master prompt exactly.
- [ ] Inter loaded; tabular figures on every number column, KPI and timestamp.
- [ ] Only token colours; no raw hex in components; dark theme separately tuned.
- [ ] Section titles outside cards; no nested cards; spacing only from the scale.
- [ ] Buttons 32 px (Standard); one primary per section; busy and disabled
      states correct.
- [ ] Tabs and segmented controls slide; drawers and dialogs animate in and out;
      reduced motion respected.
- [ ] KPI strip is a single divided card with deltas worded honestly.
- [ ] Decision detail: verdict panel with threshold-marked confidence bar;
      Record tab as a vertical timeline.
- [ ] Nothing banned in §3; every status has icon + label; AA contrast passes.
- [ ] Footer attribution present on every page.
