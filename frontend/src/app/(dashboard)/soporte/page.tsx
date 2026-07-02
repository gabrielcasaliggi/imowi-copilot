"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AgentConsole } from "@/components/soporte/AgentConsole";
import { ChatPanel } from "@/components/soporte/ChatPanel";
import { NocBoard } from "@/components/soporte/NocBoard";
import { SupportSidebar } from "@/components/soporte/SupportSidebar";
import { useApp } from "@/contexts/AppContext";

export default function SoportePage() {
  const { isAdmin, selectTicket } = useApp();
  const searchParams = useSearchParams();
  const ticketParam = searchParams.get("ticket");

  useEffect(() => {
    if (ticketParam) selectTicket(ticketParam);
  }, [ticketParam, selectTicket]);

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 gap-3 overflow-hidden">
      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)] gap-4">
        <div className="workbench-main flex flex-col min-h-0 rounded-2xl border border-slate-800/80 overflow-hidden">
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {isAdmin ? <NocBoard /> : <ChatPanel />}
          </div>
          <div className="px-3 py-2.5 border-t border-slate-800/80 shrink-0 bg-slate-950/40">
            <AgentConsole />
          </div>
        </div>
        <div className="workbench-sidebar min-h-0 rounded-2xl border border-slate-800/60 overflow-hidden">
          <SupportSidebar />
        </div>
      </div>
    </div>
  );
}
