"use client";

import Link from "next/link";

import { PageHeader } from "@/components/app/common";
import { JourneyView } from "@/components/domain/journey";
import { Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function PortalHome() {
  const { me, customerOrg } = useAuth();
  if (!customerOrg) return null;
  return (
    <>
      <PageHeader title={`Welcome, ${me?.full_name.split(" ")[0]}`} description={`Your AI journey with DeployMind for ${customerOrg.organisation_name}.`}
        actions={<>
          <Button asChild variant="outline"><Link href="/portal/support">Get support</Link></Button>
          <Button asChild><Link href="/portal/assessments/new">New assessment</Link></Button>
        </>} />
      <JourneyView orgId={customerOrg.organisation_id} base="/portal" />
    </>
  );
}
