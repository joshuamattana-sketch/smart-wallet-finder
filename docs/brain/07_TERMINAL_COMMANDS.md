# Terminal Commands

## Main Folder
`C:\Users\Joshua\Desktop\wallet finder`

Use for:
- Python scripts
- tests
- git from repo root

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

## Web Folder

`C:\Users\Joshua\Desktop\wallet finder\lumora-web`

Use for:

- Next.js build
- Next.js dev server

```
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"npm run buildnpm run dev
```

## Python Tests

```
cd "C:\Users\Joshua\Desktop\wallet finder"python -m pytest tests/test_local_heatmap_live.pypython -m compileall scripts services tests
```

## Local Live Writer

```
cd "C:\Users\Joshua\Desktop\wallet finder"python scripts/run_local_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT --timeframes 5m,15m,1h --active-interval 2 --background-interval 10 --samples 999999 --max-frames 900 --target live
```

## Local + Live Compatibility

```
cd "C:\Users\Joshua\Desktop\wallet finder"python scripts/run_local_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT --timeframes 5m,15m,1h --active-interval 2 --background-interval 10 --samples 999999 --max-frames 900 --target both
```

## Git Rules

Always check:

```
git status
```

Never use:

```
git add .
```

Always add explicit files only.

Never commit:

- `.env`
- `.env.local`
- `lumora-web/fixtures/live/*.json`
- `lumora-web/fixtures/heatmap/*.json`
- Supabase keys

```
## Commit Brain Notes

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
git status
git add docs/brain
git commit -m "Add Lumora project brain notes"
git push
```