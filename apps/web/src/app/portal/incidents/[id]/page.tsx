"use client";

import { use } from "react";

import { IncidentDetail } from "@/components/domain/operations";

export default function PortalIncident({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <IncidentDetail id={id} area="portal" />;
}
