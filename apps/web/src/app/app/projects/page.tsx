"use client";

import { PageHeader } from "@/components/app/common";
import { ProjectsList } from "@/components/domain/project";

export default function Projects() {
  return (<><PageHeader title="Projects" description="Discovery → Solution Design → Development → Integration → Testing → Deployment → Production → Handover." /><ProjectsList base="/app" /></>);
}
