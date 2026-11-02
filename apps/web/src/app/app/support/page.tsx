"use client";

import { useState } from "react";

import { PageHeader } from "@/components/app/common";
import { NewTicketButton, TicketList } from "@/components/domain/operations";
import { OrgSelect } from "@/components/domain/widgets";
import { useAuth } from "@/lib/auth";

export default function Support() {
  const { can } = useAuth();
  const [org, setOrg] = useState("");
  return (
    <>
      <PageHeader title="Support" description="Customer tickets with SLA tracking, assignment, internal notes and resolution history."
        actions={<><OrgSelect value={org} onChange={setOrg} allowAll />{org && can("support.write") && <NewTicketButton orgId={org} />}</>} />
      <TicketList base="/app" orgId={org || undefined} />
    </>
  );
}
