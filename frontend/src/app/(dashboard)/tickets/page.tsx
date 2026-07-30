"use client";

import { TicketQueuePanel } from "@/components/soporte/TicketQueuePanel";
import { SupervisorBoard } from "@/components/soporte/SupervisorBoard";
import { AgentsTeamPanel } from "@/components/soporte/AgentsTeamPanel";
import { AgentSelfPanel } from "@/components/soporte/AgentSelfPanel";
import { useApp } from "@/contexts/AppContext";

export default function TicketsPage() {
  const { can, isAdmin } = useApp();
  const showTeam = can("stats.agents") || can("users.manage_agents") || can("stats.global");
  const isSupervisorOps = !isAdmin && can("tickets.reassign");

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-6">
      {showTeam && <AgentsTeamPanel />}
      <AgentSelfPanel />
      {isSupervisorOps ? <SupervisorBoard /> : <TicketQueuePanel />}
    </div>
  );
}
