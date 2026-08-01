# Design System — Data Agent

Tokens extracted from existing styles.css and inline styles. Values match the current production UI exactly. Migration to CSS variables is incremental.

Source of truth: `apps/web/src/tokens.css`

---

## Color Palette

### Brand

| Token | Hex | Usage |
|---|---|---|
| `--color-primary` | `#176b87` | Primary button background, bar chart fill, readiness indicator |
| `--color-primary-hover` | `#155e75` | Button hover state (computed darken, not yet in CSS) |
| `--color-primary-light` | `#e9f4f7` | Selected project button, selected artifact item, selected context row |

### Sidebar

| Token | Hex | Usage |
|---|---|---|
| `--color-sidebar-bg` | `#10202b` | Sidebar background |
| `--color-sidebar-text` | `#f8fafc` | Sidebar base text color |
| `--color-sidebar-text-muted` | `#dce7ef` | Nav button default state |
| `--color-sidebar-hover` | `#1b3342` | Nav button hover / active background |
| `--color-sidebar-border` | `#315469` | Nav button active border, sidebar select border |
| `--color-sidebar-select-bg` | `#172f3d` | Sidebar select background |
| `--color-sidebar-label` | `#98acbd` | Section label text |
| `--color-sidebar-summary` | `#b5c5d1` | Summary stats text below project selector |

### Semantic

| Token | Hex | Usage |
|---|---|---|
| `--color-success` | `#16a34a` | Status OK icon, validation pass item |
| `--color-success-bg` | `#eef8f3` | Completed workflow step, passed validation gate, OK status badge |
| `--color-success-border` | `#b9dfca` | Border for completed steps, passed gates, OK badges |
| `--color-warning` | `#d97706` | Status warn icon |
| `--color-warning-bg` | `#fef9e7` | Warning workflow step, validation warn badge |
| `--color-warning-border` | `#f9e79f` | Border for warning steps and badges |
| `--color-error` | `#dc2626` | Status error icon, validation fail item text |
| `--color-error-bg` | `#fdf2f2` | Failed/blocked workflow step, not-passed validation gate, error status badge |
| `--color-error-border` | `#f5c6cb` | Border for error steps, gates, badges |
| `--color-info` | `#0ea5e9` | Status info icon |
| `--color-info-bg` | `#edf7fa` | Running workflow step, info status badge |
| `--color-info-border` | `#a8d4e1` | Border for running steps and info badges |

### Surface

| Token | Hex | Usage |
|---|---|---|
| `--color-page-bg` | `#f5f7fa` | `:root` background, document-level fill |
| `--color-surface` | `#ffffff` | Panel, topbar, artifact rail/stage backgrounds |
| `--color-surface-light` | `#f7f9fb` | List item cards (projects, contexts, datasets, models, skills), table header, readiness items, file artifact |
| `--color-surface-hover` | `#e9f4f7` | Selected project/context/artifact highlight |
| `--color-border` | `#dfe5ec` | Panel border, topbar border-bottom, list item borders |
| `--color-border-input` | `#c8d2dd` | Input, textarea, select borders |
| `--color-border-subtle` | `#edf1f5` | Panel header bottom border, table cell borders, bar track background |

### Text

| Token | Hex | Usage |
|---|---|---|
| `--color-text-primary` | `#1d2633` | `:root` default color, input text |
| `--color-text-secondary` | `#667789` | Panel description, list item secondary text, small labels |
| `--color-text-heading` | `#243242` | Markdown body, project button, context row button, pre text |
| `--color-text-label` | `#3e4d5f` | Form field labels, table headers, ghost button text, bar row strong |
| `--color-text-hint` | `#8899aa` | Hint text below form fields |
| `--color-text-report` | `#374151` | Report prose, table/chart titles |
| `--color-text-report-label` | `#6b7280` | Metric card labels |
| `--color-text-report-source` | `#9ca3af` | Source notes at report bottom |

---

## Chart Colors

Used by recharts in `main.tsx` (the `COLORS` array). Applied cyclically to pie chart slices and line/bar/area series.

| Token | Hex |
|---|---|
| `--color-chart-0` | `#6366f1` |
| `--color-chart-1` | `#06b6d4` |
| `--color-chart-2` | `#f59e0b` |
| `--color-chart-3` | `#ef4444` |
| `--color-chart-4` | `#10b981` |
| `--color-chart-5` | `#8b5cf6` |
| `--color-chart-6` | `#ec4899` |
| `--color-chart-7` | `#f97316` |

---

## Typography

### Font Stack

| Token | Value |
|---|---|
| `--font-sans` | Inter, "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif |
| `--font-mono` | "SFMono-Regular", Consolas, "Liberation Mono", monospace |

Sans is applied on `:root`. Mono is used for code blocks, file artifacts, and tool call summaries.

### Size Scale

| Token | Value | Where used |
|---|---|---|
| `--text-xs` | `12px` | Section labels, sidebar summary, hint text, small labels, model info |
| `--text-sm` | `13px` | Form labels, table cells, workflow step descriptions, metric deltas |
| `--text-base` | `14px` | Report prose, validation summary |
| `--text-lg` | `16px` | Panel header h2, brand logo text |
| `--text-xl` | `18px` | Widget header h2 |
| `--text-2xl` | `22px` | Markdown h1, report heading h1 |
| `--text-3xl` | `24px` | Metric card values |

### Weight Scale

| Token | Value | Where used |
|---|---|---|
| `--font-weight-semibold` | `600` | Status badges, report h2/h3 |
| `--font-weight-bold` | `700` | Report h1 |
| `--font-weight-extrabold` | `800` | Brand logo, section labels, form labels, table headers |

### Line Height

| Token | Value | Where used |
|---|---|---|
| `--leading-tight` | `1.25` | Topbar h1 |
| `--leading-normal` | `1.45` | Workflow step descriptions, tool call paragraphs |
| `--leading-relaxed` | `1.55` | Textarea, pre/code blocks |
| `--leading-prose` | `1.65` | Markdown body, report prose |

---

## Spacing

### Scale

| Token | Value | Where used |
|---|---|---|
| `--space-1` | `4px` | Panel header gap, project button inner gap, context button gap |
| `--space-2` | `8px` | Nav section gap, field row gap, list gaps, button icon gap |
| `--space-3` | `12px` | Workflow view gap, artifact rail gap, file artifact padding |
| `--space-4` | `16px` | Panel padding, structured report block gap |
| `--space-5` | `20px` | Sidebar padding |
| `--space-6` | `24px` | Sidebar section gap, empty state padding |

### Layout Tokens

| Token | Value | Where used |
|---|---|---|
| `--space-section-gap` | `18px` | Module grid gap, artifact layout gap, artifact widget padding |
| `--space-page-padding` | `22px` | Module grid padding-y, upload dropzone padding |
| `--space-page-padding-x` | `28px` | Topbar padding-x, module grid padding-x |

---

## Border Radius

| Token | Value | Where used |
|---|---|---|
| `--radius-sm` | `4px` | Validation badge, report unknown block |
| `--radius-md` | `6px` | Nav buttons, form inputs, sidebar select, list items, buttons, workflow badges, file artifact |
| `--radius-lg` | `8px` | Panels, workflow steps, upload dropzone, metric cards, validation gate |
| `--radius-full` | `999px` | Bar chart track |

---

## Surfaces (Composite Tokens)

These combine primitive tokens into reusable surface presets.

| Token | Value | Usage |
|---|---|---|
| `--surface-panel-bg` | `var(--color-surface)` | Card/panel background |
| `--surface-panel-border` | `1px solid var(--color-border)` | Card/panel border |
| `--surface-panel-radius` | `var(--radius-lg)` | Card/panel corner radius |
| `--surface-button-min-height` | `40px` | Primary/secondary/ghost buttons |
| `--surface-input-min-height` | `38px` | Input, textarea, select, nav buttons, sidebar select |

---

## Usage

`tokens.css` is the source of truth. All design values are defined there as CSS custom properties on `:root`.

styles.css should migrate to `var()` references over time. The current state uses hardcoded values; updating classes to reference tokens makes theming and consistency enforcement possible without touching every selector.

To reference a token in CSS:

```css
.example {
  color: var(--color-text-primary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}
```

Chart colors can be referenced from TypeScript via `getComputedStyle(document.documentElement).getPropertyValue('--color-chart-0')` or kept in sync with the `COLORS` array in `main.tsx`.
