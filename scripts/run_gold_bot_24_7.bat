@echo off
REM ============================================================================
REM  run_gold_bot_24_7.bat  --  Gold Bot 24/7 DEMO runner (Windows)
REM ----------------------------------------------------------------------------
REM  Runs the VALIDATED M15-swing config on a DEMO account, forever, and
REM  auto-restarts if the worker exits (crash, broker disconnect, MT5 restart).
REM
REM  DEMO ONLY. Live trading is hard-locked in the build. All safety guards
REM  (risk gate, demo-account verification, loss-streak supervisor, kill switch,
REM  SL/TP, lot sizing) stay ON. This wrapper deliberately does NOT pass
REM  --reset-safety-state, so a crash-loop can never wipe the loss-streak
REM  cooldown. If you ever need to clear a stale cooldown, run ONCE by hand:
REM    python scripts\run_gold_bot_worker.py --mode demo --auto-execute-demo ^
REM      --confirm-demo-order --m15-swing-test --reset-safety-state --max-iterations 1
REM
REM  BEFORE STARTING: MT5 must be installed, running, and logged into the
REM  DEMO account. (Optional) set the Discord webhook for phone notifications:
REM    setx LUMORA_GOLD_DISCORD_WEBHOOK_URL "https://discord.com/api/webhooks/..."
REM  To STOP: close this window, or press Ctrl+C.
REM ============================================================================

cd /d "%~dp0.."

:loop
echo.
echo [%date% %time%] starting Gold Bot worker (M15 swing, DEMO)...
python scripts\run_gold_bot_worker.py ^
  --mode demo --auto-execute-demo --confirm-demo-order ^
  --m15-swing-test ^
  --sync-outcomes-every 20 ^
  --discord-session-summary ^
  --interval-seconds 60
echo [%date% %time%] worker exited (code %errorlevel%). Restarting in 30s... (Ctrl+C to stop)
timeout /t 30 /nobreak >nul
goto loop
