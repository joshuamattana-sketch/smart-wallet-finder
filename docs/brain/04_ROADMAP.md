# Lumora Roadmap

## Current Priority
LM38 Compact:
Supabase latest heatmap payload storage.

Goal:
Writer → Supabase latest payload
→ Vercel API `source=live`
→ Online Lumora can show live heatmap data.

## Next Milestones

### LM39 — Vercel Live Env Verification
- Add Supabase env vars to Vercel.
- Confirm online `/api/heatmap?source=live` reads Supabase.
- Confirm `resolvedSource=live`.
- Confirm `stale=false`.

### LM40 — Hosted Worker
- Move writer from local PC to hosted worker.
- Worker runs continuously.
- Writes latest payloads to Supabase.
- Website remains live when local PC is off.

### LM41 — Live Reliability
- Stale detection.
- Worker health checks.
- Retry/backoff.
- Last successful update monitoring.

## Later Product Work

### DS1 — Lumora Visual Identity System
Avoid generic AI SaaS design.
Build a serious market-intelligence cockpit style.

### UX1 — Customizable Dashboard Workspaces
- User-configurable widgets.
- Saved layouts.
- Trader presets.
- Compact/pro modes.

### QA1 — Professional Quality Layer
- Regression tests.
- API contract checks.
- Loading/error state tests.
- Security checklist.