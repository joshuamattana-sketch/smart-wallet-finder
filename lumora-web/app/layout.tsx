import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lumora — Trading Intelligence Terminal",
  description: "Premium crypto market intelligence. Orderbook depth, whale tracking, liquidity maps.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-lumora-bg text-lumora-text antialiased">
        {children}
      </body>
    </html>
  );
}
