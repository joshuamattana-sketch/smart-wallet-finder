# Claude Rules

## General
- Do not commit.
- Do not push.
- Do not write secrets into files.
- Do not edit unrelated files.
- Keep changes minimal.
- Always report changed files.
- Always run requested tests/builds.

## Never Touch Unless Explicitly Asked
- `package.json`
- `next.config.*`
- `globals.css`
- `layout.tsx`
- unrelated app pages
- fixture JSON files
- `.env` files

## For Backend/Data Patches
Usually allowed:
- `scripts/*`
- `services/*`
- `tests/*`
- `lumora-web/lib/*`
- `lumora-web/app/api/*`
- `supabase/*`
- docs

Do not edit UI pages unless explicitly listed.

## For UI Patches
Usually allowed:
- specific `page.tsx`
- specific component file
- types if needed

Do not edit API/backend unless explicitly listed.

## Required Output After Every Patch
1. Changed files
2. What changed
3. Tests/build result
4. Manual steps
5. Files not touched