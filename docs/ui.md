# Web UI

The web UI is a React + TypeScript single-page app in `frontend/`. It talks to the backend only through the
[web API](api.md): REST for data and server-sent events for live progress. It has two routes.

## 1. Upload (`/`)

- **Drop zone.** A single source file or a `.zip` project, with the size limits shown up front. Rejected
  archives come back with the backend's reason (zip slip, too many files, and so on).
- **Review depth.** *Static only*, *Quick*, *Standard* or *Deep*, each with a one-line explanation. The
  meanings are in [LLM review](review.md).
- **Models and consent.** The panel lists the configured models from `GET /api/providers`, marks each as
  hosted or local, and shows any provider that is paused (rate limited or failing). Code goes to hosted
  models only after the reviewer ticks the consent box, and the box says what happens without it: only the
  local model reviews, or only static analysis runs. Mock mode is labeled as such.

## 2. Scan (`/scans/:id`)

While the scan runs, the page follows `GET /api/scans/{id}/events`:

- **Pipeline rail.** Unpacking, parsing and chunking, running analyzers, AI review, cross-checking and
  summarizing, with the active stage pulsing.
- **Analyzers.** Each tool with its state, finding count and duration. A tool that is not installed shows
  as skipped, and the scan continues.
- **Model lanes.** One lane per provider. Every call is a mark: answered or served from the cache, or a
  call that fell back to another provider (rate limited, unavailable, invalid answer). Routing decisions are
  visible as they happen.
- **Live counters and findings.** Severity counts and the newest findings, as they are confirmed.

`EventSource` reconnects on its own and sends `Last-Event-ID`, so a dropped connection resumes where it
stopped instead of replaying the whole scan. The stream is closed when the scan is done or failed.

When the scan finishes, the same URL becomes the results workspace, so a finished scan can be bookmarked
or shared within the retention window.

## 3. Results

- **Quality score** with its grade and the formula that produced it, and the **AI summary** (headline,
  risks, next steps).
- **Report downloads:** HTML, JSON and SARIF.
- **Filters:** severity, category and source (an analyzer or a model). Findings the reviewer rejected or
  the AI dismissed, and AI-only findings below 0.6 confidence, are hidden by default; a toggle shows how
  many there are and brings them back.
- **Three panes that scroll independently:**
  - *Files*, with the finding count and highest severity of each.
  - *Code*, read-only and syntax highlighted, with a severity mark in the gutter for every finding. The
    selected finding's lines are highlighted and scrolled to the middle of the pane.
  - *Findings*, as cards: severity, location, category, CWE, which analyzers and models found it, who
    verified it, confidence, the message, why it matters, the evidence quoted from the code, and a
    suggested change. **Accept** and **Reject** are saved with `PATCH` and change the counts and score.
- **Which model saw which file:** for each provider, how many calls it answered, what happened to the
  others (rate limited, unavailable, invalid answer) and the files it was sent. This is the privacy record
  for hosted providers.

## 4. State and data flow

| Data | Where it lives | Why |
|---|---|---|
| Providers, scan detail, findings, files | TanStack Query | Caching, loading and error states; a decision invalidates the affected queries. |
| The live scan | A Zustand store fed by `EventSource` | Events are applied in order; findings are keyed by id, so a later event (for example, after verification) replaces the earlier one. |
| Filters, selection | Component state | Nothing else needs them. |

API types are generated, never hand-written. `backend/scripts/export_openapi.py` writes
`backend/openapi.json`, and `npm run api-types` turns it into `frontend/src/api/schema.d.ts`. CI regenerates
both and fails if either differs from the committed file, so the client cannot drift from the server.

## 5. Design

The visual idea is **ink in the margin**: a calm reading surface where findings are marks beside the code,
the way an editor marks a manuscript.

- **Tokens.** Colors, radii and fonts are Tailwind v4 `@theme` tokens in `src/index.css`. Components use
  tokens only, and shadcn/ui's semantic colors are mapped onto them.
- **Type.** Bricolage Grotesque for headings, IBM Plex Sans for text, IBM Plex Mono for code, all
  self-hosted through Fontsource, so the UI makes no requests to font CDNs.
- **Light and dark** themes, following the system setting until the reviewer picks one.
- **Severity is never color alone.** Every severity chip carries its name, and gutter marks carry a
  screen-reader label and a tooltip with the finding titles.
- **Keyboard.** Every control is reachable with Tab and has a visible focus ring; `j` and `k` move between
  findings.
- **Motion.** One small animation (marks ticking in) and smooth scrolling in the panes, both turned off
  when the system asks for reduced motion.

### Why Prism instead of Monaco

The code pane only needs to display code with line marks. Monaco is a full editor: several megabytes of
JavaScript and workers that its React wrapper loads from a CDN by default. Prism highlights on the client in
a few kilobytes, bundles with the app, and leaves the gutter as plain, accessible HTML.

## 6. Tests

Vitest with Testing Library, no network:

- the store reducer (stages, tools, plan, finding replacement, calls, reset per scan);
- the findings filter;
- the pane-scrolling and evidence-dedent helpers;
- an app-level flow with a stubbed `fetch` and a hand-driven fake `EventSource`: upload with and without
  consent, a live scan turning into results, and rejecting a finding.

Run them with `npm test`.
