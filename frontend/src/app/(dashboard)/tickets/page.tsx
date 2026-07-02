"use client";

import { TicketQueuePanel } from "@/components/soporte/TicketQueuePanel";

export default function TicketsPage() {
  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <TicketQueuePanel />
    </div>
  );
}
