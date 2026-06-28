# Lumora live schalten + Besucher zählen (Schritt für Schritt)

Ziel: Seite live auf Vercel, Google Analytics zählt Besucher (auch die von TikTok),
Sicherheit steht. Reihenfolge genau so abarbeiten. Du brauchst keinen Code anzufassen.

---

## Teil A — Google Analytics 4 anlegen (die Mess-ID holen)

1. Geh auf https://analytics.google.com und melde dich mit deinem Google-Konto an.
2. Links unten **Verwaltung** (Zahnrad) → **Property erstellen**.
   - Name: `Lumora`. Zeitzone Zürich (Schweiz), Währung nach Wahl. Weiter bis fertig.
3. Es fragt nach einer **Datenerfassung / Plattform**: wähle **Web**.
   - Website-URL: deine Domain `lumora-app.app`. Stream-Name: `Lumora Web`.
4. Danach zeigt es dir eine **Mess-ID** in der Form `G-XXXXXXXXXX`.
   **Diese ID kopieren** und kurz parken (brauchst du in Teil C).

Mehr musst du in GA jetzt nicht tun. Den Tracking-Code baut die Seite selbst ein.

---

## Teil B — Auf Vercel deployen

1. Geh auf https://vercel.com → **Sign up** → **Continue with GitHub**
   (mit dem Konto, dem `github.com/joshuamattana-sketch/smart-wallet-finder` gehört).
2. **Add New… → Project** → in der Liste `smart-wallet-finder` **Import**.
3. Vercel erkennt Next.js automatisch. **Wichtig — Root Directory setzen:**
   - Bei *Root Directory* auf **Edit** klicken und `lumora-web` auswählen.
     (Die App liegt im Unterordner, nicht im Repo-Wurzelverzeichnis.)
4. **Noch NICHT auf Deploy.** Erst die Umgebungsvariablen aus Teil C eintragen
   (Abschnitt *Environment Variables* auf derselben Seite). Dann **Deploy**.
5. Nach 1–2 Minuten gibt dir Vercel eine Test-URL (`...vercel.app`). Die geht sofort.

### Eigene Domain (optional, aber besser für TikTok)
Vercel → dein Projekt → **Settings → Domains** → Domain eintragen und den
angezeigten DNS-Eintrag bei deinem Domain-Anbieter setzen. Danach in Teil C
`NEXT_PUBLIC_SITE_URL` auf genau diese Domain setzen und einmal neu deployen.

---

## Teil C — Umgebungsvariablen (Environment Variables)

In Vercel beim Import unter *Environment Variables* eintragen (oder später unter
**Settings → Environment Variables**). Pro Zeile: Name links, Wert rechts.
Nach Änderungen einmal **Redeploy** drücken, sonst greifen sie nicht.

| Name | Wert | Pflicht? |
|------|------|----------|
| `NEXT_PUBLIC_GA_ID` | deine `G-XXXXXXXXXX` aus Teil A | ja (sonst kein Zählen) |
| `NEXT_PUBLIC_SITE_URL` | `https://lumora-app.app` | ja |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Projekt-URL (`https://xxx.supabase.co`) | ja |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase **publishable**-Key (`sb_publishable_…`) | ja |
| `SUPABASE_URL` | gleiche Supabase-URL wie oben | ja |
| `SUPABASE_ANON_KEY` | Supabase **anon**-Key (langer `eyJ…`-String) | ja |
| `LUMORA_ACCESS_SECRET` | langer Zufallswert (siehe unten) | ja |
| `LUMORA_ENABLE_GOLD_BOT_COMMANDS` | `false` | ja, muss `false` bleiben |
| `NEXT_PUBLIC_DISCORD_URL` | dein Discord-Invite | optional |

**Supabase-Keys finden:** supabase.com → dein Projekt → **Settings → API**.
Dort stehen Project URL, anon key und publishable key.

**`LUMORA_ACCESS_SECRET` erzeugen:** irgendein langer Zufallsstring (40+ Zeichen).
Z. B. auf https://www.uuidgenerator.net/ zweimal eine UUID erzeugen und
aneinanderhängen. Diesen Wert geheim halten. Ändern = alle Beta-Logins fliegen raus.

> Hinweis Live-Daten: Die Heatmap/Whale-Daten brauchen separat laufende Daten-Writer
> (siehe `docs/PRODUCTION_LIVE_HEATMAP_PLAN.md`). Landing-Page und Warteliste
> funktionieren auch ohne das. Für den TikTok-Push reicht die Landing-Page.

---

## Teil D — Rechtliches (Impressum + Datenschutz) — ERLEDIGT

Betreiber sitzt in der **Schweiz** (Privatperson). Impressum + Datenschutz sind
bereits ausgefüllt und auf Schweizer Recht umgestellt:

- **Impressum** (`/impressum`): Schweizer UWG Art. 3 Abs. 1 lit. s — Joshua Mattana,
  8200 Schaffhausen, `legal.lumora@gmail.com`. (Kein deutsches DDG, keine EU-OS-Plattform.)
- **Datenschutz** (`/datenschutz`): Schweizer revDSG primär, DSGVO zusätzlich für
  EU-Besucher. Bearbeiter: Vercel (Hosting), Supabase (DB), Google Analytics (nur
  nach Zustimmung). Aufsicht: EDÖB Bern.
- In `lumora-web/lib/site.ts` ist `LEGAL_DETAILS_FILLED = true` → keine Warnbanner mehr.

**Noch offen (vor echtem Traffic prüfen):**

1. **Provider-Adressen verifizieren** — die Adressen von Vercel / Supabase / Google
   in `PROCESSORS` (site.ts) gegen deren aktuelle DPA/Datenschutz-Seiten gegenchecken.
2. **Strasse nachtragen**, sobald Lumora bezahlte Pläne anbietet (E-Commerce →
   vollständige Adresse Pflicht). Feld `OPERATOR.street` in site.ts, aktuell leer.
3. **Anwaltlicher Check** empfohlen — die Texte sind Templates, kein Rechtsrat,
   besonders der CH+EU-Doppelansatz.

---

## Teil E — TikTok-Links, damit GA "TikTok" als Quelle zeigt

Häng an deinen Link sogenannte UTM-Parameter. Dann siehst du in GA sauber, wie
viele über TikTok kamen, statt nur "direct".

Statt nur `https://lumora-app.app` nimm in der TikTok-Bio / Pinned-Comment:

```
https://lumora-app.app/?utm_source=tiktok&utm_medium=social&utm_campaign=launch1
```

- `utm_source=tiktok` → erscheint in GA als Quelle "tiktok"
- `utm_campaign=launch1` → pro Video/Kampagne hochzählen (`launch2`, `launch3`, …),
  dann siehst du, welches Video am meisten brachte.

In GA findest du das unter **Berichte → Akquisition → Zugriffsquellen**.

---

## Teil F — Nach dem Deploy: prüfen, dass gezählt wird

1. Öffne deine Live-URL im Browser. Unten kommt das Cookie-Banner →
   **Akzeptieren** klicken (sonst lädt GA bei dir absichtlich nicht).
2. In GA: **Berichte → Echtzeit**. Innerhalb ~30 Sek. solltest du dich selbst
   als 1 aktiven Nutzer sehen.
3. Sieht man nichts: prüfen, ob `NEXT_PUBLIC_GA_ID` in Vercel korrekt gesetzt ist
   und ob nach dem Setzen **neu deployt** wurde.

### Schon eingebaut (musst du nichts tun)
- Cookie-Consent-Banner (DSGVO): GA lädt **erst nach Zustimmung**, Ablehnen ist
  gleichwertig. Wahl wird gespeichert, Banner kommt nur einmal.
- Security-Header inkl. Content-Security-Policy (blockt fremde Skripte/iframes,
  erlaubt nur GA + Supabase + eigene Inhalte).
- Warteliste mit Rate-Limit + E-Mail-Validierung, Invite-Gate für die App-Routen.
