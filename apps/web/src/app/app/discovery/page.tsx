"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { OrgSelect } from "@/components/domain/widgets";
import { Button, Card, Dialog, DialogContent, Field, Input, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, relativeTime } from "@/lib/utils";

export default function Discovery() {
  const { can } = useAuth();
  const router = useRouter();
  const q = useQuery({ queryKey: ["sessions"], queryFn: () => api("/discovery/sessions?page_size=100") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ organisation_id: "", title: "", session_date: "" });
  const create = useMutation({ mutationFn: () => api("/discovery/sessions", { method: "POST", body: { ...f, session_date: f.session_date || null } }),
    onSuccess: (s) => router.push(`/app/discovery/${s.id}`), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <>
      <PageHeader title="Discovery" description="Structured technical discovery: requirements, integrations, stakeholders and risks."
        actions={can("discovery.write") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <Button onClick={() => setOpen(true)}>New discovery session</Button>
            <DialogContent title="New discovery session">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
                <Field label="Organisation" htmlFor="s-org"><OrgSelect id="s-org" value={f.organisation_id} onChange={(v) => setF({ ...f, organisation_id: v })} /></Field>
                <Field label="Title" htmlFor="s-title"><Input id="s-title" required minLength={2} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
                <Field label="Session date" htmlFor="s-date"><Input id="s-date" type="date" value={f.session_date} onChange={(e) => setF({ ...f, session_date: e.target.value })} /></Field>
                <div className="flex justify-end"><Button type="submit" loading={create.isPending} disabled={!f.organisation_id || f.title.length < 2}>Create</Button></div>
              </form>
            </DialogContent>
          </Dialog>)} />
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No discovery sessions yet" /> : (
          <Card><Table><thead><tr><Th>Session</Th><Th>Organisation</Th><Th>Status</Th><Th>Owner</Th><Th>Date</Th><Th>Updated</Th></tr></thead><tbody>
            {d.items.map((s: any) => (
              <tr key={s.id} className="hover:bg-muted/40"><Td><Link href={`/app/discovery/${s.id}`} className="font-medium hover:underline">{s.title}</Link></Td><Td>{s.organisation_name}</Td>
                <Td><StatusBadge status={s.status} /></Td><Td>{s.owner_name ?? "—"}</Td><Td className="text-xs">{formatDate(s.session_date)}</Td><Td className="text-xs">{relativeTime(s.updated_at)}</Td></tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
