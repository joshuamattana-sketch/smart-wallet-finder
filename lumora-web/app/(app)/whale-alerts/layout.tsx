import type { Metadata } from "next";

export const metadata: Metadata = { title: "Whale Alerts" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
