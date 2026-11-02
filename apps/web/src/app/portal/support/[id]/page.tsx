"use client";

import { use } from "react";

import { TicketDetail } from "@/components/domain/operations";

export default function PortalTicket({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <TicketDetail id={id} area="portal" />;
}
