"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { OrgSelect } from "@/components/domain/widgets";
import { Badge, Button, Dialog, DialogContent, Field, Input, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Apps() {
  const { can } = useAuth();
  const router = useRouter();
  const q = useQuery({ queryKey: ["apps"], queryFn: () => api<any[]>("/apps") });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api("/projects?page_size=100") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ organisation_id: "", project_id: "", name: "", description: "" });
  const create = useMutation({ mutationFn: () => api("/apps", { method: "POST", body: { ...f, project_id: f.project_id || null } }),
    onSuccess: (a) => router.push(`/app/apps/${a.id}`), onError: (e) => toast.error(errorMessage(e)) });
  const orgProjects = (projects.data?.items ?? []).filter((p: any) => p.organisation_id === f.organisation_id);
  return (
    <>
      <PageHeader title="AI applications" description="Enterprise knowledge assistants delivered to customers: configuration, documents, evaluation and deployment."
        actions={can("app.write") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <Button onClick={() => setOpen(true)}>New application</Button>
            <DialogContent title="New knowledge assistant" description="Development, staging and production environments are created automatically.">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
                <Field label="Organisation" htmlFor="a-org"><OrgSelect id="a-org" value={f.organisation_id} onChange={(v) => setF({ ...f, organisation_id: v, project_id: "" })} /></Field>
                <Field label="Project" htmlFor="a-proj"><Select id="a-proj" value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">None</option>{orgProjects.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
                <Field label="Name" htmlFor="a-name"><Input id="a-name" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
                <Field label="Description" htmlFor="a-desc"><Textarea id="a-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
                <div className="flex justify-end"><Button type="submit" disabled={!f.organisation_id || f.name.length < 2} loading={create.isPending}>Create</Button></div>
              </form>
            </DialogContent>
          </Dialog>)} />
      <QueryView q={q}>
        {(list) => list.length === 0 ? <EmptyState icon={Bot} title="No AI applications yet" /> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {list.map((a) => (
              <Link key={a.id} href={`/app/apps/${a.id}`} className="rounded-xl border bg-card p-5 transition hover:border-primary/40 hover:shadow-sm">
                <div className="flex items-start justify-between gap-2"><p className="font-semibold">{a.name}</p><StatusBadge status={a.status} /></div>
                <p className="text-sm text-muted-foreground">{a.organisation_name}</p>
                <p className="mt-2 line-clamp-2 text-sm">{a.description}</p>
                <div className="mt-3 flex flex-wrap gap-1.5"><Badge>{a.provider}:{a.model}</Badge>{a.grounded_mode && <Badge tone="success">Grounded</Badge>}<Badge>prompt {a.prompt_version}</Badge></div>
              </Link>
            ))}
          </div>
        )}
      </QueryView>
    </>
  );
}
