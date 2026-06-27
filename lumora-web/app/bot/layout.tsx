import type { Metadata, Viewport } from "next";
import { FintechNav } from "@/components/fintech/FintechNav";
import { FintechFooter } from "@/components/fintech/FintechFooter";
import { BOT_BRAND } from "@/lib/bot-brand";

export const metadata: Metadata = {
  title: { default: `${BOT_BRAND.product} · ${BOT_BRAND.tagline}`, template: `%s · ${BOT_BRAND.name}` },
  description: BOT_BRAND.blurb,
  applicationName: BOT_BRAND.name,
  alternates: { canonical: "/bot" },
  openGraph: {
    type: "website",
    siteName: BOT_BRAND.name,
    title: `${BOT_BRAND.product} · ${BOT_BRAND.tagline}`,
    description: BOT_BRAND.blurb,
    url: "/bot",
    locale: "en_US",
  },
  robots: { index: true, follow: true },
};

// This brand is LIGHT — override the root dark theme/colorScheme for /bot.
export const viewport: Viewport = {
  themeColor: "#FFFFFF",
  colorScheme: "light",
};

// The data-theme wrapper scopes the fintech tokens; the explicit white bg +
// ink text overrides the root <body> dark theme for everything under /bot.
export default function BotLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-theme="fintech"
      className="fx-page min-h-screen bg-fintech-bg font-sans text-fintech-ink antialiased"
    >
      <FintechNav />
      <main>{children}</main>
      <FintechFooter />
    </div>
  );
}
