"use client";

import { ROLES } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { KeyValue, PageHeader, QueryView } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Field, Input, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, relativeTime } from "@/lib/utils";

export default function PortalOrganisation() {
  const { customerOrg, can } = useAuth();
  const qc = useQueryClient();
  const orgId = customerOrg?.organisation_id;
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api(`/organisations/${orgId}`), enabled: !!orgId });
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => api<any[]>(`/organisations/${orgId}/members`), enabled: !!orgId });
  const [form, setForm] = useState({ full_name: "", email: "", role: "customer", temporary_password: "" });
  const add = useMutation({ mutationFn: () => api(`/organisations/${orgId}/members`, { method: "POST", body: form }),
    onSuccess: () => { toast.success("Member added — share the temporary password securely"); setForm({ full_name: "", email: "", role: "customer", temporary_password: "" }); qc.invalidateQueries({ queryKey: ["members", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)) });
  if (!orgId) return null;
  return (
    <>
      <PageHeader title="Organisation" description="Your organisation profile and team members." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Card><CardHeader><CardTitle>Profile</CardTitle></CardHeader><CardContent>
          <QueryView q={org}>{(o: any) => <KeyValue items={[["Name", o.name], ["Industry", o.industry], ["Size", o.size], ["Website", o.website], ["Country", o.country], ["Customer since", formatDate(o.created_at)]]} />}</QueryView>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Members</CardTitle></CardHeader><CardContent className="space-y-4">
          <QueryView q={members}>{(list) => (
            <Table><thead><tr><Th>Name</Th><Th>Role</Th><Th>Last sign-in</Th></tr></thead><tbody>
              {list.map((m) => <tr key={m.user_id}><Td><p className="font-medium">{m.full_name}</p><p className="text-xs text-muted-foreground">{m.email}</p></Td><Td><Badge>{ROLES[m.role as keyof typeof ROLES] ?? m.role}</Badge></Td><Td className="text-xs">{relativeTime(m.last_login_at)}</Td></tr>)}
            </tbody></Table>)}
          </QueryView>
          {can("users.manage") && (
            <form className="grid gap-3 border-t pt-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
              <Field label="Full name" htmlFor="m-name"><Input id="m-name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required minLength={2} /></Field>
              <Field label="Email" htmlFor="m-email"><Input id="m-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></Field>
              <Field label="Role" htmlFor="m-role"><Select id="m-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="customer">Customer</option><option value="viewer">Viewer</option><option value="org_admin">Organisation Admin</option></Select></Field>
              <Field label="Temporary password" htmlFor="m-pw" hint="10+ chars, letter and digit"><Input id="m-pw" type="password" value={form.temporary_password} onChange={(e) => setForm({ ...form, temporary_password: e.target.value })} required minLength={10} /></Field>
              <div className="sm:col-span-2"><Button type="submit" loading={add.isPending}>Add member</Button></div>
            </form>
          )}
        </CardContent></Card>
      </div>
    </>
  );
}
