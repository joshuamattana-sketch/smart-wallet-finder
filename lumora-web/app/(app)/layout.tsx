import type { Metadata } from "next";
import { TopNav } from "@/components/nav/TopNav";
import { SiteFooter } from "@/components/ui/SiteFooter";

// Private beta surface — keep every gated route out of search indexes.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

// LM69C: deep navy terminal backdrop — a near-black indigo base with one
// very faint cool radial wash falling from the top, so pages read as a lit
// instrument bay instead of flat black-gray. No dot grid, no hero glow; the
// instruments still own the depth.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-[#0a0b10] bg-[radial-gradient(ellipse_90%_55%_at_50%_-15%,rgba(99,102,241,0.07),transparent_65%)]">
      <TopNav />
      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-5 sm:px-6 lg:px-8">
        {children}
      </main>
      <SiteFooter variant="slim" />
    </div>
  );
}
