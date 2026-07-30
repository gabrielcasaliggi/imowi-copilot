"use client";

import { TicketQueuePanel } from "@/components/soporte/TicketQueuePanel";
import { AgentsTeamPanel } from "@/components/soporte/AgentsTeamPanel";
import { useApp } from "@/contexts/AppContext";

export default function TicketsPage() {
  const { can } = useApp();
  const showTeam = can("stats.agents") || can("users.manage_agents") || can("stats.global");

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-6">
        {showTeam && <AgentsTeamPanel />}
        <TicketQueuePanel />
      </div>
    </div>
  );
}
