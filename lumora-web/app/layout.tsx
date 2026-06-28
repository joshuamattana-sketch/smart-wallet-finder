import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Fraunces } from "next/font/google";
import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import { AnalyticsConsent } from "@/components/analytics/AnalyticsConsent";
import {
  SITE_URL,
  SITE_NAME,
  SITE_TITLE as TITLE,
  SITE_DESCRIPTION as DESCRIPTION,
} from "@/lib/site";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s · Lumora" },
  description: DESCRIPTION,
  applicationName: "Lumora",
  keywords: [
    "crypto trading terminal",
    "liquidity intelligence",
    "orderbook depth",
    "liquidity heatmap",
    "whale tracking",
    "order flow",
    "funding rate",
    "open interest",
    "sweep risk",
    "market intelligence",
    "BTC",
    "ETH",
  ],
  authors: [{ name: "Lumora" }],
  creator: "Lumora",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "Lumora",
    title: TITLE,
    description: DESCRIPTION,
    url: "/",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/opengraph-image.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
};

export const viewport: Viewport = {
  themeColor: "#0c0c0e",
  colorScheme: "dark",
};

// Self-hosted, preloaded, metric-matched fonts (next/font) — replaces the
// render-blocking Google Fonts @import and removes the swap reflow on the H1.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});
// Display face for the hero headline + section titles — characterful editorial
// grotesque, deliberately not Inter/Space-Grotesk. Candidate under evaluation.
const display = Fraunces({
  subsets: ["latin"],
  display: "swap",
  weight: ["600"],
  style: ["normal", "italic"],
  variable: "--font-display",
});

// Structured data — static server-side @graph, no user input, so the JSON-LD
// injection has no XSS surface. Reuses the shared site constants.
const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      logo: `${SITE_URL}/icon.svg`,
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: DESCRIPTION,
      publisher: { "@id": `${SITE_URL}/#organization` },
    },
    {
      "@type": "SoftwareApplication",
      name: SITE_NAME,
      applicationCategory: "FinanceApplication",
      operatingSystem: "Web",
      description: DESCRIPTION,
      url: SITE_URL,
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable} ${display.variable}`}>
      <body className="min-h-screen bg-lm-bg text-lm-text antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        {children}
        <AnalyticsConsent />
        <Analytics />
      </body>
    </html>
  );
}
