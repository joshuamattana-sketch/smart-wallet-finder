import { TopNav } from "@/components/nav/TopNav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-lumora-bg">
      <TopNav />
      <main className="mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>
    </div>
  );
}
