import type { Metadata, Viewport } from "next";
import "./globals.css";

// Production origin. Override per-environment with NEXT_PUBLIC_SITE_URL so OG /
// canonical URLs resolve to the real domain instead of this placeholder.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://lumora.app";

const TITLE = "Lumora — Trading Intelligence Terminal";
const DESCRIPTION =
  "Lumora is a liquidity intelligence terminal for crypto — orderbook depth, whale flow, funding, open interest, liquidity heatmaps and sweep-risk zones, distilled into a single market read.";

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-lm-bg text-lm-text antialiased">
        {children}
      </body>
    </html>
  );
}
