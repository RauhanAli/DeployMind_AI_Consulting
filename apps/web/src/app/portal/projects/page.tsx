"use client";

import { PageHeader } from "@/components/app/common";
import { ProjectsList } from "@/components/domain/project";

export default function PortalProjects() {
  return (<><PageHeader title="Projects" description="Track delivery progress, milestones and shared tasks." /><ProjectsList base="/portal" /></>);
}
