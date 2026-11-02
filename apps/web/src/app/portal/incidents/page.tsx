"use client";

import { PageHeader } from "@/components/app/common";
import { IncidentList } from "@/components/domain/operations";

export default function PortalIncidents() {
  return (<><PageHeader title="Incident updates" description="Status updates for service incidents affecting your applications." /><IncidentList base="/portal" /></>);
}
