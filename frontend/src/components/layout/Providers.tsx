"use client";

import type { ReactNode } from "react";
import { AppProvider } from "@/contexts/AppContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ToastProvider } from "@/components/ui/Toast";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppProvider>{children}</AppProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
