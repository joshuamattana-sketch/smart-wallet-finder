import { TopNav } from "@/components/nav/TopNav";

// LM69B: flat terminal background — the dot-grid texture is gone so the
// instruments (chart, heatmap, tape) own all the visual depth on a page.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-lm-bg">
      <TopNav />
      <main className="mx-auto max-w-screen-2xl px-4 py-5 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
