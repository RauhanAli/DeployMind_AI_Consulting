"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/app/common";
import { NewTicketButton, TicketList } from "@/components/domain/operations";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function PortalSupport() {
  const { can } = useAuth();
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api("/projects") });
  return (
    <>
      <PageHeader title="Support" description="Raise and track support requests. SLA targets depend on priority."
        actions={can("support.write") && <NewTicketButton projects={projects.data?.items} />} />
      <TicketList base="/portal" />
    </>
  );
}
