# Patch Context Mini

## Current architecture

- `app.py` should stay thin and should not be edited unless explicitly requested.
- UI files should only be edited in UI-specific patches.
- API routes should only be edited in API-specific patches.
- `services/` contains pure Python engines and business logic.
- `tests/` contains deterministic local tests.
- `docs/brain/` contains project context and terminal commands.
- Supabase SQL lives in `supabase/`.
- Discord logic is split into formatter, sender, and filter services.
- Signal flow: heatmap history -> wall events -> persistence features -> setup classifier -> signal builder -> signal journal -> alerts.
- Whale flow starts with whale event detection, then formatter/filter/sender later.

## Completed patches

- LM45 heatmap history
- LM46 wall events
- LM47 wall persistence features
- LM48 setup classifier
- LM49 signal builder
- LM50 signal journal
- LM51A discord formatter
- LM51B discord webhook sender
- LM51C discord alert filter
- LM52A whale alert engine

## Rules

- No UI unless requested.
- No API route changes unless requested.
- No secrets.
- No commit/push.
- Tests must be local and deterministic.
- No network in tests.
- Keep patches small.
- Edit only listed files.

## Standard test commands

```bash
python -m pytest <target_test>
python -m compileall services tests