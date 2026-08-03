"use client";

import { useEffect, type ReactNode } from "react";
import { AppProvider } from "@/contexts/AppContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ToastProvider } from "@/components/ui/Toast";
import { applyBranding, hydrateBranding } from "@/lib/brand";
import { api } from "@/lib/api-client";

function BrandHydrator({ children }: { children: ReactNode }) {
  useEffect(() => {
    void api
      .publicBranding()
      .then((b) => applyBranding(b))
      .catch(() => {
        void hydrateBranding();
      });
  }, []);
  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <BrandHydrator>
          <AppProvider>{children}</AppProvider>
        </BrandHydrator>
      </ToastProvider>
    </ThemeProvider>
  );
}
