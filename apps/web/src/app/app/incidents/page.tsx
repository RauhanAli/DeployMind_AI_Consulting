"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app/common";
import { IncidentList } from "@/components/domain/operations";
import { OrgSelect } from "@/components/domain/widgets";
import { Button, Dialog, DialogContent, Field, Input, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Incidents() {
  const { can } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ organisation_id: "", title: "", description: "", severity: "sev3", app_id: "", environment_id: "" });
  const apps = useQuery({ queryKey: ["apps"], queryFn: () => api<any[]>("/apps") });
  const envs = useQuery({ queryKey: ["envs", f.app_id], queryFn: () => api<any[]>(`/apps/${f.app_id}/environments`), enabled: !!f.app_id });
  const create = useMutation({ mutationFn: () => api("/incidents", { method: "POST", body: { ...f, app_id: f.app_id || null, environment_id: f.environment_id || null } }),
    onSuccess: (i) => router.push(`/app/incidents/${i.id}`), onError: (e) => toast.error(errorMessage(e)) });
  const orgApps = (apps.data ?? []).filter((a) => a.organisation_id === f.organisation_id);
  return (
    <>
      <PageHeader title="Incidents" description="Open → Investigating → Identified → Resolved → Closed, with customer notifications."
        actions={can("incident.write") && (
          <Dialog open={open} onOpenChange={setOpen}><Button onClick={() => setOpen(true)}>Declare incident</Button>
            <DialogContent title="Declare an incident">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
                <Field label="Organisation" htmlFor="i-org"><OrgSelect id="i-org" value={f.organisation_id} onChange={(v) => setF({ ...f, organisation_id: v, app_id: "", environment_id: "" })} /></Field>
                <Field label="Title" htmlFor="i-t"><Input id="i-t" required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
                <Field label="Description" htmlFor="i-d"><Textarea id="i-d" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Severity" htmlFor="i-s"><Select id="i-s" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>{["sev1", "sev2", "sev3", "sev4"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
                  <Field label="Application" htmlFor="i-a"><Select id="i-a" value={f.app_id} onChange={(e) => setF({ ...f, app_id: e.target.value, environment_id: "" })}><option value="">—</option>{orgApps.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</Select></Field>
                  <Field label="Environment" htmlFor="i-e"><Select id="i-e" value={f.environment_id} onChange={(e) => setF({ ...f, environment_id: e.target.value })}><option value="">—</option>{(envs.data ?? []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
                </div>
                <div className="flex justify-end"><Button type="submit" disabled={!f.organisation_id || f.title.length < 3} loading={create.isPending}>Declare</Button></div>
              </form>
            </DialogContent></Dialog>)} />
      <IncidentList base="/app" />
    </>
  );
}
