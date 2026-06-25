# Gold Bot — 24/7 DEMO auf einem Windows-VPS

Ziel: Der Gold Bot läuft rund um die Uhr auf einem Windows-Server (VPS), tradet auf
deinem **Demo-Konto** (kein echtes Geld), und du schaust per Handy zu. Dein eigener
PC kann aus sein.

**Wichtig vorab**
- **Demo only.** Live/Echtgeld ist im Code hart gesperrt. Alle Sicherheits-Guards bleiben an.
- Der Bot braucht **MetaTrader 5 (MT5)** — das ist **nur Windows**. Darum ein *Windows*-VPS, nicht der Linux-Railway-Worker.
- Validierte Strategie: **M15-Swing** (wenige Trades, Halten über Stunden). Nicht M1-Scalp (kein Edge).
- Käufe/Logins (VPS mieten, MT5-Login) machst **du** — Passwörter/Kontodaten gibst nur du ein.

---

## 1. Windows-VPS mieten

Du brauchst einen kleinen Windows-Server, der 24/7 läuft. Empfehlung (eins aussuchen):

- **Forex-VPS** (z. B. ForexVPS.net, Cheap-Forex-VPS) — auf MT5 zugeschnitten, ~5–20 €/Monat. Einfachster Weg.
- **Amazon Lightsail (Windows)** — ~8–16 $/Monat, zuverlässig.
- Alternativ: Vultr/Contabo/Azure mit Windows-Image.

Spec: **2 vCPU, 4 GB RAM, Windows Server**, ~40 GB Disk. Reicht locker für MT5 + Bot.

> Tipp: Server-Region nah am Broker (oft London/NY) = weniger Latenz. Für Demo egal.

---

## 2. Mit dem VPS verbinden (auch vom Handy)

- **Vom PC:** Windows-Taste → „Remotedesktopverbindung" → IP + Login vom VPS-Anbieter eingeben.
- **Vom Handy:** App **„Microsoft Remote Desktop"** (iOS/Android) installieren → selbe IP/Login. So schaust du unterwegs zu.

---

## 3. Auf dem VPS: MetaTrader 5 installieren + Demo einloggen

1. Im VPS einen Browser öffnen → MT5 von deinem Broker (oder metatrader5.com) herunterladen, installieren.
2. MT5 starten → **mit deinem DEMO-Konto einloggen** (Login/Passwort/Server vom Broker). **Du** gibst das ein.
3. MT5 **offen lassen** — der Bot hängt sich an das laufende, eingeloggte Terminal an.
4. Chart „XAUUSD" (Gold) öffnen, damit das Symbol verfügbar ist.

---

## 4. Python + Bot-Abhängigkeiten installieren

1. Im VPS-Browser **python.org** → Python 3.11+ herunterladen.
2. Installer starten → **Häkchen „Add python.exe to PATH" setzen** → Install.
3. „Eingabeaufforderung" (cmd) öffnen, eintippen:
   ```
   pip install MetaTrader5 pandas requests
   ```
   (Falls beim ersten Lauf ein Modul fehlt: `pip install <name>` nachziehen.)

---

## 5. Den Bot-Code auf den VPS kopieren

Einfachster Weg ohne Git:
1. Auf deinem PC den Projektordner `wallet finder` als **ZIP** packen.
2. ZIP per Remotedesktop ins VPS ziehen (Copy-Paste funktioniert über RDP), z. B. nach `C:\gold-bot`.
3. Im VPS entpacken.

(Wer Git nutzt: stattdessen `git clone <dein-repo>` — auch ok.)

---

## 6. Testlauf (sendet NICHTS)

cmd im Projektordner öffnen und einmal im Beobachten-Modus laufen lassen:
```
python scripts\run_gold_bot_worker.py --mode observe --max-iterations 1
```
- Erwartung: verbindet zu MT5, liest Konto/Gold-Daten, schreibt eine Entscheidung, **keine Order**.
- Fehler „MT5 not running / not demo"? → MT5 offen + Demo eingeloggt? Symbol XAUUSD da?

---

## 7. 24/7 starten

Im Projektordner liegt fertig: **`scripts\run_gold_bot_24_7.bat`**.

- **Erststart (einmalig, räumt alte Cooldown-Sperre auf):**
  ```
  python scripts\run_gold_bot_worker.py --mode demo --auto-execute-demo --confirm-demo-order --m15-swing-test --reset-safety-state --max-iterations 1
  ```
- **Dann Dauerbetrieb:** Doppelklick auf `run_gold_bot_24_7.bat`.
  Der läuft endlos, M15-Swing, Demo, und **startet sich nach Crash automatisch neu**.

Was die `.bat` macht: validierte Config (`--m15-swing-test`), Outcome-Sync alle 20 Runden,
Discord-Zusammenfassung beim Stop, 60s-Takt. Kein `--reset-safety-state` im Loop → Crash-Neustart
kann die Loss-Streak-Sperre nicht aushebeln.

---

## 8. Dass es nach Neustart/Reboot von selbst wieder läuft (empfohlen: NSSM)

Eine `.bat` stirbt, wenn der VPS rebootet. Damit der Bot **automatisch beim Hochfahren** startet:

1. **NSSM** herunterladen (nssm.cc), entpacken, `nssm.exe` z. B. nach `C:\nssm`.
2. cmd **als Administrator** öffnen:
   ```
   C:\nssm\nssm.exe install GoldBot24x7
   ```
3. Im Fenster:
   - **Path:** `C:\gold-bot\scripts\run_gold_bot_24_7.bat` (dein Pfad)
   - **Startup directory:** `C:\gold-bot`
   - Tab **„Exit actions" → Restart** (Standard ist ok)
   - **Install service**.
4. Starten: `C:\nssm\nssm.exe start GoldBot24x7`

Jetzt läuft der Bot als Windows-Dienst: startet bei Boot, restartet bei Crash.
Stoppen: `C:\nssm\nssm.exe stop GoldBot24x7`.

> Hinweis: MT5 muss nach einem Reboot ebenfalls automatisch starten + eingeloggt sein
> (MT5 merkt sich den Login normalerweise; ggf. MT5-Verknüpfung in den Autostart legen).

---

## 9. Vom Handy überwachen

- **Discord-Benachrichtigungen** (empfohlen): auf dem VPS einmal setzen, dann postet der Bot Zusammenfassungen:
  ```
  setx LUMORA_GOLD_DISCORD_WEBHOOK_URL "https://discord.com/api/webhooks/DEIN_WEBHOOK"
  ```
  (Webhook in deinem Discord-Server unter Kanal → Einstellungen → Integrationen → Webhooks anlegen.)
- **Live zusehen:** „Microsoft Remote Desktop"-App → VPS → du siehst MT5 mit offenen Demo-Trades.
- Der Bot schreibt außerdem `data/gold_bot/worker_status.json` (aktueller Stand).

---

## 10. Stoppen / Sicherheit

- **Stoppen:** `.bat`-Fenster schließen, oder NSSM-Dienst stoppen (Schritt 8).
- **Not-Aus:** Umgebungsvariable `GOLD_BOT_KILL_SWITCH=true` setzen → Bot sendet keine Orders mehr.
- **Guards (immer an):** Demo-Konto-Verifikation, Risk-Gate (Tagesverlust-Budget, Margin),
  Loss-Streak-Cooldown, Macro-Lockout, SL/TP, Lot-Sizing. Live bleibt hart gesperrt.

---

## Der Befehl im Klartext (was 24/7 läuft)

```
python scripts\run_gold_bot_worker.py \
  --mode demo --auto-execute-demo --confirm-demo-order \
  --m15-swing-test \
  --sync-outcomes-every 20 \
  --discord-session-summary \
  --interval-seconds 60
```

- `--m15-swing-test` = die validierte M15-Swing-Config (positiv 2025 UND 2026 out-of-sample).
- `--mode demo --auto-execute-demo --confirm-demo-order` = darf Demo-Orders senden (alle drei nötig).
- Erwartung: **wenige Trades** (Swing, Halten über Stunden) — das ist gewollt, nicht ein Fehler.
