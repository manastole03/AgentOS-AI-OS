# Design system

The UI is built on Tailwind CSS v4 and Radix primitives, published from
`packages/typescript/ui` and imported as `@healthos/ui/<component>`.

## Stack

| Concern | Choice |
|---|---|
| Styling | Tailwind CSS v4 (CSS-first config, no `tailwind.config.ts`) |
| Primitives | Radix UI, wrapped shadcn-style with `cva` variants |
| Data fetching | TanStack Query v5 |
| Tables | TanStack Table v8 |
| Forms | react-hook-form + zod |
| Charts | Recharts v3 |
| Motion | Motion (framer-motion successor) |
| Toasts | Sonner |
| Theming | next-themes, class-based dark mode |
| Command palette | cmdk |
| Icons | lucide-react |

All are open source and installed into the workspace.

## Tokens

Tokens live in `apps/web/app/globals.css`. Surface and brand colors are OKLCH so light and dark
steps stay perceptually even. Chart series colors are pinned hex — see the palette section.

```
Surfaces   background foreground card popover muted accent border input ring
Brand      primary secondary            (a calm clinical teal)
Status     success warning serious critical info      ← RESERVED, see below
Series     chart-1 … chart-8
Sequential seq-100 seq-250 seq-400 seq-550 seq-700
Sidebar    sidebar sidebar-foreground sidebar-primary sidebar-accent sidebar-border
Roles      role-patient role-doctor role-hospital role-insurance role-admin
```

Typography is Plus Jakarta Sans for UI and JetBrains Mono for clinical values, patient IDs, and
codes. Anything numeric that needs to align down a column gets the `tabular` class, which turns on
tabular numerals — clinical values are read by scanning, and proportional digits break that.

## Chart palette — validated, not chosen by eye

The categorical palette is **formally validated** in both light and dark against the exact app
surfaces, using the data-visualization validator (lightness band, chroma floor, colorblind
separation, normal-vision separation, contrast).

```
Light (surface #ffffff)   ALL CHECKS PASS
  worst adjacent CVD ΔE 9.1 (protan) · worst adjacent normal-vision ΔE 19.6
  3 slots below 3:1 contrast → relief rule applies (visible labels or table view)

Dark  (surface #131b19)   ALL CHECKS PASS
  worst adjacent CVD ΔE 8.4 (protan) · worst adjacent normal-vision ΔE 19.3
  all 8 slots ≥ 3:1 contrast
```

The dark surface token is pinned to `#131b19` precisely because that is the surface the palette
was validated against.

**Do not edit a series color without re-validating.** The slot *order* is the colorblind-safety
mechanism, not decoration — adjacent pairs are what get compared in a stacked bar or a legend.

Slots 1–3 are safe for all-pairs comparison (scatter, choropleth, small multiples). Past three,
rely on adjacent-pair ordering, direct labels, or faceting.

## Visualization rules

These are correctness rules, enforced by the `chart` component's API rather than left to
discipline:

1. **Series colors are assigned in fixed order by series identity** — never cycled, never by sort
   rank. A filter that changes the series count must not repaint the survivors.
2. **No dual-axis charts.** Two measures of different scale are two charts. The wrapper exposes no
   `yAxisId` escape hatch. (Blood pressure systolic + diastolic on one chart is fine — same unit.)
3. **Text wears text tokens**, never the series color.
4. **Legend whenever there are ≥ 2 series**; direct labels when ≤ 4. Never a number on every point.
5. **Status colors are reserved** and never appear in `CHART_SERIES`.
6. **Every status is icon + text**, never color alone — that is what `status-badge` is for.
7. Grid and axes recessive; 2px lines; tooltips on by default, because an HTML chart is
   interactive.

## Components

43 components, one concern per file.

| Group | Components |
|---|---|
| Layout & feedback | `card` `tabs` `accordion` `collapsible` `separator` `scroll-area` `progress` `avatar` `skeleton` `breadcrumb` `alert` `section` `page-header` `sidebar-nav` `theme-toggle` |
| Overlays | `dialog` `alert-dialog` `sheet` `popover` `tooltip` `hover-card` `dropdown-menu` |
| Forms | `form` `input` `textarea` `label` `select` `checkbox` `radio-group` `switch` `slider` `toggle` `toggle-group` `button` |
| Data | `data-table` `pagination` `command` `empty-state` `status-badge` `stat-tile` `table` `badge` |
| Charts | `chart` |

Three carry most of the domain weight:

- **`status-badge`** — the clinical status component. A `cva` over the reserved status tones that
  always renders an icon *and* a text label. Exports `statusTone`, mapping domain statuses
  (`approved`, `denied`, `overdue`, `abnormal`, `critical`, …) to a tone, so status rendering is
  consistent across every workspace.
- **`stat-tile`** — the KPI tile. The value is the hero number: large, `font-mono tabular`. A delta
  renders an arrow icon *and* a sign, never color alone.
- **`data-table`** — generic over `TData`, with sortable headers (`aria-sort`), search, pagination,
  a loading skeleton, and an empty state. No `any`.

Twelve components are intentionally **not** marked `"use client"` — they contain no hooks and no
event handlers, so they stay server-renderable and out of the client bundle.

## Conventions

```tsx
import { cn } from "@healthos/utils";          // clsx + tailwind-merge
import { cva, type VariantProps } from "class-variance-authority";
```

`React.forwardRef` with a `displayName`, named exports only, double quotes, semicolons, 2-space
indent. Accessibility is not optional: real labels, `aria-*`, keyboard support, and a visible
focus ring (`focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`).

## Tailwind v4 notes

The migration from v3 removed `tailwind.config.ts` entirely. Three things are easy to get wrong:

- **`@source` is required for the workspace UI package.** It sits outside the app root, so without
  `@source "../../../packages/typescript/ui/src"` every `@healthos/ui` class is purged from the
  build.
- **`theme.container` is gone.** It is re-declared as `@utility container`.
- **`tailwindcss-animate` is replaced by `tw-animate-css`**, and PostCSS now uses
  `@tailwindcss/postcss` with autoprefixer removed (v4 handles prefixing).

## Adding a component

1. Create `packages/typescript/ui/src/<name>.tsx`.
2. Add a `"./<name>": "./src/<name>.tsx"` entry to that package's `exports` map.
3. `pnpm exec tsc --noEmit` in the package, then in `apps/web`.

If it renders data, check it against the visualization rules above before shipping.
