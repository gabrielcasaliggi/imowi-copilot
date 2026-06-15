"use client";

import { useEffect } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { useApp } from "@/contexts/AppContext";

function BrandSync({ children }: { children: React.ReactNode }) {
  const { tenantContext } = useApp();

  useEffect(() => {
    const color = tenantContext?.brand_color || "#22d3ee";
    document.documentElement.style.setProperty("--brand", color);
  }, [tenantContext?.brand_color]);

  return <>{children}</>;
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <BrandSync>
        <div className="flex flex-col h-screen max-w-[1600px] mx-auto w-full">
          <AppHeader />
          <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
            <SidebarNav />
            <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
              {children}
            </main>
          </div>
        </div>
      </BrandSync>
    </AuthGuard>
  );
}
