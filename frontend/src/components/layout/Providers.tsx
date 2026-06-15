"use client";

import type { ReactNode } from "react";
import { AppProvider } from "@/contexts/AppContext";

export function Providers({ children }: { children: ReactNode }) {
  return <AppProvider>{children}</AppProvider>;
}
