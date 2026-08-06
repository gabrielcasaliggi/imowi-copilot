"use client";

import { Suspense } from "react";
import { InboxPanel } from "@/components/inbox/InboxPanel";

export default function InboxPage() {
  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <Suspense fallback={<p className="p-4 text-sm text-slate-500">Cargando bandeja…</p>}>
        <InboxPanel />
      </Suspense>
    </div>
  );
}
