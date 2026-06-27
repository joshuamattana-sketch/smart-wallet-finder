import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { TopNav } from "@/components/nav/TopNav";
import { SiteFooter } from "@/components/ui/SiteFooter";
import { ACCESS_COOKIE, verifyAccessToken } from "@/lib/access";

// Private beta surface — keep every gated route out of search indexes.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

// Defense in depth: the edge middleware already gates these routes, but auth
// must never rely on a single layer. This server-side check re-verifies the
// signed access cookie before any gated page renders, so a middleware bypass
// (matcher gap, header trick, framework CVE) still can't leak the app.
export const dynamic = "force-dynamic";

// LM69C: deep navy terminal backdrop — a near-black indigo base with one
// very faint cool radial wash falling from the top, so pages read as a lit
// instrument bay instead of flat black-gray. No dot grid, no hero glow; the
// instruments still own the depth.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const token = cookies().get(ACCESS_COOKIE)?.value;
  if (!(await verifyAccessToken(token))) redirect("/enter");

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
