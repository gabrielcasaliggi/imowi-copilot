"use client";

import { AgentConsole } from "@/components/soporte/AgentConsole";
import { ChatPanel } from "@/components/soporte/ChatPanel";
import { NocBoard } from "@/components/soporte/NocBoard";
import { SupportSidebar } from "@/components/soporte/SupportSidebar";
import { useApp } from "@/contexts/AppContext";

export default function SoportePage() {
  const { isAdmin } = useApp();

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 gap-3 overflow-hidden">
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 flex flex-col min-h-0 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          {isAdmin ? <NocBoard /> : <ChatPanel />}
          <div className="p-3 border-t border-slate-800 shrink-0">
            <AgentConsole />
          </div>
        </div>
        <SupportSidebar />
      </div>
    </div>
  );
}
