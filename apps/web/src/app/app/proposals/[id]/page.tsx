"use client";

import { use } from "react";

import { ProposalDetail } from "@/components/domain/proposal";

export default function InternalProposal({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <ProposalDetail id={id} area="internal" />;
}
