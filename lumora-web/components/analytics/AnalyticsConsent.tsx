"use client";

import { useCallback, useEffect, useState } from "react";
import Script from "next/script";
import { usePathname } from "next/navigation";

// LM78A — GDPR-clean Google Analytics 4 with a consent gate.
//
// The whole point: no Google script, no cookie, no network call to Google
// happens until the visitor explicitly clicks "Accept". Declining is exactly
// as easy as accepting (DSGVO requires equal weight). The choice is stored in
// localStorage so the banner only shows once.
//
// GA is a no-op unless NEXT_PUBLIC_GA_ID (a "G-XXXXXXXXXX" measurement id) is
// set, so local dev and preview deploys never send data.

const CONSENT_KEY = "lumora_consent_v1";
const GA_ID = process.env.NEXT_PUBLIC_GA_ID;

type Consent = "granted" | "denied";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

function readStoredConsent(): Consent | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(CONSENT_KEY);
    return v === "granted" || v === "denied" ? v : null;
  } catch {
    return null;
  }
}

export function AnalyticsConsent() {
  // `null` until we have read localStorage on the client, so SSR and the first
  // client render agree (no hydration mismatch) and the banner never flashes.
  const [consent, setConsent] = useState<Consent | null>(null);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setConsent(readStoredConsent());
    setMounted(true);
  }, []);

  const choose = useCallback((value: Consent) => {
    try {
      window.localStorage.setItem(CONSENT_KEY, value);
    } catch {
      // Private mode / storage blocked: keep the choice for this session only.
    }
    setConsent(value);
  }, []);

  // Send a page_view on client-side route changes. The initial load (with any
  // ?utm_* params) is captured by the gtag config below, so this only needs the
  // path for in-app navigations.
  useEffect(() => {
    if (consent !== "granted" || !GA_ID) return;
    if (typeof window.gtag !== "function") return;
    window.gtag("event", "page_view", { page_path: pathname });
  }, [pathname, consent]);

  const showGa = consent === "granted" && Boolean(GA_ID);
  const showBanner = mounted && consent === null;

  return (
    <>
      {showGa && (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
            strategy="afterInteractive"
          />
          <Script id="ga-init" strategy="afterInteractive">
            {`
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', '${GA_ID}');
            `}
          </Script>
        </>
      )}

      {showBanner && (
        <div
          role="dialog"
          aria-label="Cookie- und Analyse-Einwilligung"
          className="fixed inset-x-3 bottom-3 z-[100] mx-auto max-w-2xl animate-fade-in rounded-2xl border border-lm-border bg-lm-surface/95 p-5 shadow-glass backdrop-blur-md sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-relaxed text-lm-text-dim">
              Wir nutzen Analyse-Cookies (Google Analytics), um zu verstehen, wie
              die Seite genutzt wird. Nur mit deiner Zustimmung. Mehr dazu in der{" "}
              <a
                href="/datenschutz"
                className="text-lm-text underline decoration-lm-purple/60 underline-offset-2 hover:decoration-lm-purple"
              >
                Datenschutzerklärung
              </a>
              .
            </p>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => choose("denied")}
                className="rounded-lg border border-lm-border px-4 py-2 text-sm font-medium text-lm-text-dim transition-colors hover:bg-white/5 hover:text-lm-text"
              >
                Ablehnen
              </button>
              <button
                type="button"
                onClick={() => choose("granted")}
                className="rounded-lg bg-lm-purple px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#7c4ddb]"
              >
                Akzeptieren
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
