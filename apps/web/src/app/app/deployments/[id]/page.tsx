"use client";

import { use } from "react";

import { DeploymentDetail } from "@/components/domain/deploy";

export default function DeploymentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <DeploymentDetail id={id} />;
}
