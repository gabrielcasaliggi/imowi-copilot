"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AgentConsole } from "@/components/soporte/AgentConsole";
import { ChatPanel } from "@/components/soporte/ChatPanel";
import { NocBoard } from "@/components/soporte/NocBoard";
import { SupportSidebar } from "@/components/soporte/SupportSidebar";
import { useApp } from "@/contexts/AppContext";

type MobileTab = "chat" | "contexto";

export default function SoportePage() {
  const { isAdmin, can, selectTicket, ticketFormacion } = useApp();
  const searchParams = useSearchParams();
  const ticketParam = searchParams.get("ticket");
  const showSidebar = isAdmin || Boolean(ticketFormacion) || can("tickets.reassign");
  const [mobileTab, setMobileTab] = useState<MobileTab>("chat");

  useEffect(() => {
    if (ticketParam) void selectTicket(ticketParam);
  }, [ticketParam, selectTicket]);

  useEffect(() => {
    if (ticketFormacion?.id) setMobileTab("chat");
  }, [ticketFormacion?.id]);

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 gap-3 overflow-hidden">
      {showSidebar && (
        <div className="xl:hidden flex gap-1 p-1 rounded-xl border border-slate-800 bg-slate-950/50 shrink-0">
          <button
            type="button"
            onClick={() => setMobileTab("chat")}
            className={`flex-1 text-xs font-medium py-2 rounded-lg transition-colors ${
              mobileTab === "chat"
                ? "bg-cyan-500/15 text-cyan-200 border border-cyan-500/30"
                : "text-slate-400 border border-transparent"
            }`}
          >
            Chat
          </button>
          <button
            type="button"
            onClick={() => setMobileTab("contexto")}
            className={`flex-1 text-xs font-medium py-2 rounded-lg transition-colors ${
              mobileTab === "contexto"
                ? "bg-cyan-500/15 text-cyan-200 border border-cyan-500/30"
                : "text-slate-400 border border-transparent"
            }`}
          >
            Contexto
          </button>
        </div>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)] gap-4">
        <div
          className={`workbench-main flex flex-col min-h-0 rounded-2xl border border-slate-800/80 overflow-hidden ${
            showSidebar && mobileTab === "contexto" ? "hidden xl:flex" : "flex"
          }`}
        >
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {isAdmin ? <NocBoard /> : <ChatPanel />}
          </div>
          {isAdmin && (
            <div className="px-3 py-2.5 border-t border-slate-800/80 shrink-0 bg-slate-950/40">
              <AgentConsole />
            </div>
          )}
        </div>
        {showSidebar && (
          <div
            className={`workbench-sidebar min-h-0 rounded-2xl border border-slate-800/60 overflow-hidden ${
              mobileTab === "chat" ? "hidden xl:block" : "block"
            }`}
          >
            <SupportSidebar />
          </div>
        )}
      </div>
    </div>
  );
}
