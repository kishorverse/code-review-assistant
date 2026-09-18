# Web API

The FastAPI backend runs the same pipeline as the CLI and adds four things:
- background scans
- live progress over server-sent events
- reviewer decisions on findings
- report downloads

Interactive documentation is served at `/docs` while the server runs.

```bash
cd backend
uv run uvicorn app.main:create_app --factory --reload
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/scans` | Upload a source file or `.zip` and start a scan |
| `GET` | `/api/scans/{id}` | Status; counts, quality score, AI summary and model calls once done |
| `GET` | `/api/scans/{id}/events` | Live progress as server-sent events |
| `GET` | `/api/scans/{id}/findings` | Every finding, whatever its status |
| `PATCH` | `/api/scans/{id}/findings/{finding_id}` | Accept, reject or restore a finding |
| `GET` | `/api/scans/{id}/files` | Scanned files with reported finding counts, and skipped files |
| `GET` | `/api/scans/{id}/files/{path}` | The text of one scanned file, for the code viewer |
| `GET` | `/api/scans/{id}/report?format=json\|sarif\|html` | Report download |
| `DELETE` | `/api/scans/{id}` | Stop the scan if running and delete everything it stored |
| `GET` | `/api/providers` | Enabled LLM providers and their circuit-breaker state |
| `GET` | `/api/health` | Liveness and version |

There is deliberately no endpoint that lists scans. A scan id (122 random bits) is known only to whoever submitted the scan, which is what keeps scans private in this prototype without accounts.

## Starting a scan

```bash
curl -F file=@project.zip -F depth=standard -F allow_external=true http://127.0.0.1:8000/api/scans
```

| Form field | Default | Meaning |
|---|---|---|
| `file` | required | A source file or a `.zip` of a project |
| `depth` | `standard` | `static`, `quick`, `standard` or `deep` (see [LLM review](review.md)) |
| `allow_external` | `false` | Whether hosted LLM providers may receive the code; without it only a local model is used |

The upload is extracted while the request is open, so an unsafe or broken archive is refused at once:

| Status | When |
|---|---|
| `202` | Accepted. The body is the scan: `id`, `source`, `status` (`queued`), `depth`, `allow_external`, `created_at` |
| `400` | The archive was rejected. The body has `detail` and a stable `reason` such as `path_traversal`, `compression_ratio` or `too_many_files` |
| `411` | The request did not declare `Content-Length` |
| `413` | The upload exceeds 20 MB; refused before the body is read |
| `422` | A form field is invalid |
| `503` | Too many scans are pending; retry after the `Retry-After` seconds |

At most `MAX_CONCURRENT_SCANS` scans run at once (2 by default), and later scans wait with status `queued`. At most five times that many may be pending, so a flood of uploads cannot fill the disk.

## Following progress

`GET /api/scans/{id}/events` streams every event of the scan in order, then live events until it finishes. Each event has:
- a numeric `id`, so a reconnecting `EventSource` resumes after `Last-Event-ID` automatically
- an `event` name equal to its `kind`
- a JSON `data` payload

| `event` | Payload |
|---|---|
| `status` | `status` (`queued`, `running`, `done`, `failed`) and an optional `message`. `done` or `failed` is always last. |
| `stage` | `stage`: `ingesting`, `preprocessing`, `analyzing`, `reviewing`, `verifying`, `summarizing`, `done` |
| `tool` | An analyzer started or finished: `tool`, `state`, `finding_count`, `duration_ms`, `message` |
| `finding` | A finding, as in `/findings`. A later event with the same `id` replaces the earlier one. |
| `review_plan` | `review_chunks`, `style_chunks`, `skipped_chunks` |
| `llm_call` | One model call attempt: `task`, `provider`, `model`, `status`, `latency_ms`, token counts, `detail`, `file_path`. Never prompts or responses. |

```js
const events = new EventSource(`/api/scans/${id}/events`)
events.addEventListener('finding', (e) => upsert(JSON.parse(e.data).finding))
events.addEventListener('status', (e) => {
  if (['done', 'failed'].includes(JSON.parse(e.data).status)) events.close()
})
```

## Results

Results are available once the status is `done`. Before that, `/findings`, `/files` and `/report` answer `409`.

- **`GET /api/scans/{id}`** adds `summary` (counts of reported findings and of those not reported, by reason), `score` (the quality score with its formula and inputs), `ai_summary`, and `calls` (every model call attempt: task, provider, model, status, latency, tokens and file, the record of which model saw which file).
- **`PATCH /api/scans/{id}/findings/{finding_id}`** takes `{"status": "accepted" | "rejected" | "open"}`. `open` restores a finding dismissed by AI review or rejected earlier. Counts, the score and every later report download reflect the decision. Statuses set by AI review (`dismissed_by_ai`, `needs_review`) cannot be set this way.
- **`GET /api/scans/{id}/files/{path}`** serves only paths that are among the scan's extracted files; anything else, including traversal attempts, is `404`.
- **`GET /api/scans/{id}/report`** returns an attachment with `X-Content-Type-Options: nosniff`, so the HTML report is downloaded rather than rendered in the API's origin. SARIF output validates against the SARIF 2.1.0 schema.

## Errors

| Status | Meaning |
|---|---|
| `404` | Unknown scan, finding or file. Unknown and malformed scan ids get the same `{"detail": "Scan not found"}`, so ids cannot be probed. |
| `409` | The scan has not finished, or it failed |
| `422` | Invalid request, including a status a reviewer may not set |

A scan that hits an unexpected error ends with status `failed` and a generic message; details go to the server log only. A scan that was queued or running when the server stopped is reported as `failed` with "interrupted by a server restart".

## Storage and retention

Each scan keeps everything in its own workspace under `STORAGE_DIR`:

| Directory | Contents |
|---|---|
| `upload/` | The raw upload |
| `source/` | The extracted files |
| `scratch/` | The analyzers' empty working directory |
| `results/` | `scan.json`, `events.jsonl` and `report.json`, written atomically |

A scan is found again after a restart from these files. Workspaces older than `RETENTION_HOURS` (24 by default) are deleted every 15 minutes, and `DELETE` removes one immediately, so uploaded code and everything derived from it disappear together.

Every lookup is by scan id, and a scan's data expires with its code. That makes files inside the workspace a better fit than a database: there is no schema to migrate, and nothing survives the workspace by accident.
