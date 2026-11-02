"use client";

import { use } from "react";

import { ProjectDetail } from "@/components/domain/project";

export default function PortalProject({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <ProjectDetail id={id} area="portal" />;
}
