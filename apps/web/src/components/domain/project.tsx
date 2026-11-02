"use client";

import { PROJECT_STAGES, TASK_STATUSES, label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, CircleDot, Link2, Lock, MessageSquare, Paperclip, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import {
  Badge, Button, Card, CardContent, Dialog, DialogContent, Field, Input, Progress, Select,
  Tabs, TabsContent, TabsList, TabsTrigger, Textarea,
} from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDate, relativeTime } from "@/lib/utils";

export function ProjectDetail({ id, area }: { id: string; area: "portal" | "internal" }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const write = area === "internal" && can("project.write");
  const p = useQuery({ queryKey: ["project", id], queryFn: () => api(`/projects/${id}`) });
  const timeline = useQuery({ queryKey: ["project-timeline", id], queryFn: () => api(`/projects/${id}/timeline`) });
  const stage = useMutation({ mutationFn: (s: string) => api(`/projects/${id}/stage`, { method: "POST", body: { stage: s } }),
    onSuccess: () => { toast.success("Stage updated"); qc.invalidateQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["project-timeline", id] }); },
    onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={p} rows={6}>
      {(project: any) => {
        const idx = PROJECT_STAGES.indexOf(project.stage);
        const next = PROJECT_STAGES[idx + 1];
        return (
          <>
            <PageHeader title={project.name} back={{ href: area === "portal" ? "/portal/projects" : "/app/projects", label: "Projects" }}
              description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={project.status} />{project.organisation_name} · {formatDate(project.start_date)} → {formatDate(project.target_date)}</span>}
              actions={write && next && <Button onClick={() => stage.mutate(next)} loading={stage.isPending}>Advance to {label(next)}</Button>} />
            <Card className="mb-6">
              <CardContent className="space-y-4 p-5">
                <div className="flex items-center justify-between text-sm"><span className="font-medium">Overall progress</span><span>{project.progress}% · {project.tasks_done}/{project.tasks_total} tasks</span></div>
                <Progress value={project.progress} />
                <ol className="grid grid-cols-4 gap-2 sm:grid-cols-8">
                  {PROJECT_STAGES.map((s, i) => (
                    <li key={s} className="flex flex-col items-center gap-1 text-center">
                      {i < idx ? <CheckCircle2 className="size-5 text-success" /> : i === idx ? <CircleDot className="size-5 text-primary" /> : <Circle className="size-5 text-muted-foreground" />}
                      <span className={cn("text-[11px] leading-tight", i === idx ? "font-semibold" : "text-muted-foreground")}>{label(s)}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
            <Tabs defaultValue={area === "internal" ? "board" : "timeline"}>
              <TabsList>
                {area === "internal" && <TabsTrigger value="board">Board</TabsTrigger>}
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="milestones">Milestones</TabsTrigger>
                {area === "portal" && <TabsTrigger value="tasks">Shared tasks</TabsTrigger>}
              </TabsList>
              {area === "internal" && <TabsContent value="board"><Board projectId={id} write={write} /></TabsContent>}
              <TabsContent value="timeline">
                <QueryView q={timeline}>
                  {(t: any) => (
                    <Card><CardContent className="p-5">
                      {t.activity.length === 0 ? <EmptyState title="No activity yet" /> : (
                        <ol className="relative space-y-4 border-l pl-6">
                          {t.activity.map((a: any) => (
                            <li key={a.id}><span className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-card bg-primary" />
                              <p className="text-sm">{a.message}</p><p className="text-xs text-muted-foreground">{a.actor_name ?? "System"} · {relativeTime(a.created_at)}</p></li>
                          ))}
                        </ol>
                      )}
                    </CardContent></Card>
                  )}
                </QueryView>
              </TabsContent>
              <TabsContent value="milestones"><Milestones projectId={id} write={write} /></TabsContent>
              {area === "portal" && <TabsContent value="tasks"><SharedTasks projectId={id} /></TabsContent>}
            </Tabs>
          </>
        );
      }}
    </QueryView>
  );
}

function SharedTasks({ projectId }: { projectId: string }) {
  const q = useQuery({ queryKey: ["tasks", projectId], queryFn: () => api<any[]>(`/projects/${projectId}/tasks`) });
  return (
    <QueryView q={q}>
      {(tasks) => tasks.length === 0 ? <EmptyState title="No shared tasks" /> : (
        <Card><CardContent className="divide-y p-0">
          {tasks.map((t) => <div key={t.id} className="flex items-center justify-between p-4 text-sm"><span>{t.title}</span><StatusBadge status={t.status} /></div>)}
        </CardContent></Card>
      )}
    </QueryView>
  );
}

function Milestones({ projectId, write }: { projectId: string; write: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["milestones", projectId], queryFn: () => api<any[]>(`/projects/${projectId}/milestones`) });
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const inv = () => { qc.invalidateQueries({ queryKey: ["milestones", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };
  const add = useMutation({ mutationFn: () => api(`/projects/${projectId}/milestones`, { method: "POST", body: { title, due_date: due || null } }),
    onSuccess: () => { setTitle(""); setDue(""); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const patch = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => api(`/milestones/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <QueryView q={q}>
      {(ms) => (
        <Card><CardContent className="space-y-3 p-5">
          {ms.map((m) => (
            <div key={m.id} className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
              <div className="min-w-0 flex-1"><p className="font-medium">{m.title}</p><p className="text-xs text-muted-foreground">Due {formatDate(m.due_date)}{m.completed_at && ` · completed ${formatDate(m.completed_at)}`}</p></div>
              {write ? (
                <Select aria-label={`Status of ${m.title}`} className="w-36" value={m.status} onChange={(e) => patch.mutate({ id: m.id, status: e.target.value })}>
                  {["pending", "in_progress", "done"].map((s) => <option key={s} value={s}>{label(s)}</option>)}
                </Select>
              ) : <StatusBadge status={m.status} />}
            </div>
          ))}
          {ms.length === 0 && <EmptyState title="No milestones yet" />}
          {write && (
            <form className="flex flex-wrap gap-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); if (title.trim().length >= 2) add.mutate(); }}>
              <Input placeholder="New milestone" value={title} onChange={(e) => setTitle(e.target.value)} className="min-w-48 flex-1" aria-label="Milestone title" />
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-44" aria-label="Due date" />
              <Button type="submit" loading={add.isPending} disabled={title.trim().length < 2}><Plus /> Add</Button>
            </form>
          )}
        </CardContent></Card>
      )}
    </QueryView>
  );
}

function Board({ projectId, write }: { projectId: string; write: boolean }) {
  const qc = useQueryClient();
  const tasks = useQuery({ queryKey: ["tasks", projectId], queryFn: () => api<any[]>(`/projects/${projectId}/tasks`) });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any[]>("/users/staff") });
  const [open, setOpen] = useState<any | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const inv = () => { qc.invalidateQueries({ queryKey: ["tasks", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };
  const move = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => api(`/tasks/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const add = useMutation({ mutationFn: () => api(`/projects/${projectId}/tasks`, { method: "POST", body: { title: newTitle, status: "todo" } }),
    onSuccess: () => { setNewTitle(""); inv(); }, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={tasks}>
      {(list) => (
        <>
          {write && (
            <form className="mb-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (newTitle.trim().length >= 2) add.mutate(); }}>
              <Input placeholder="Add a task…" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} aria-label="New task title" />
              <Button type="submit" loading={add.isPending} disabled={newTitle.trim().length < 2}><Plus /> Add task</Button>
            </form>
          )}
          <div className="grid gap-3 overflow-x-auto md:grid-cols-5">
            {TASK_STATUSES.map((s) => {
              const col = list.filter((t) => t.status === s);
              return (
                <div key={s} className="min-w-56 rounded-xl bg-muted/60 p-2"
                  onDragOver={(e) => write && e.preventDefault()}
                  onDrop={(e) => { const tid = e.dataTransfer.getData("text/task"); if (tid && write) move.mutate({ id: tid, status: s }); }}>
                  <div className="flex items-center justify-between px-1 pb-2"><span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label(s)}</span><Badge>{col.length}</Badge></div>
                  <div className="space-y-2">
                    {col.map((t) => (
                      <button key={t.id} draggable={write} onDragStart={(e) => e.dataTransfer.setData("text/task", t.id)} onClick={() => setOpen(t)}
                        className="w-full rounded-lg border bg-card p-3 text-left text-sm shadow-xs transition hover:border-primary/40 cursor-pointer">
                        <p className="font-medium">{t.title}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          <StatusBadge status={t.priority} />
                          {t.blocked && <Badge tone="danger"><Lock className="size-3" /> Blocked</Badge>}
                          {t.customer_visible && <Badge tone="primary">Customer</Badge>}
                          {t.comment_count > 0 && <span className="flex items-center gap-0.5"><MessageSquare className="size-3" />{t.comment_count}</span>}
                          {t.assignee_name && <span className="ml-auto">{t.assignee_name.split(" ")[0]}</span>}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          {write && <p className="mt-2 text-xs text-muted-foreground">Drag cards between columns, or open a task to change its status. Tasks with unfinished dependencies cannot be completed.</p>}
          {open && <TaskDialog task={open} all={list} staff={staff.data ?? []} write={write} onClose={() => setOpen(null)} onChange={inv} />}
        </>
      )}
    </QueryView>
  );
}

function TaskDialog({ task, all, staff, write, onClose, onChange }: { task: any; all: any[]; staff: any[]; write: boolean; onClose: () => void; onChange: () => void }) {
  const qc = useQueryClient();
  const current = all.find((t) => t.id === task.id) ?? task;
  const comments = useQuery({ queryKey: ["task-comments", task.id], queryFn: () => api<any[]>(`/tasks/${task.id}/comments`) });
  const files = useQuery({ queryKey: ["task-files", task.id], queryFn: () => api<any[]>(`/tasks/${task.id}/attachments`) });
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(true);
  const patch = useMutation({ mutationFn: (b: any) => api(`/tasks/${task.id}`, { method: "PATCH", body: b }), onSuccess: onChange, onError: (e) => toast.error(errorMessage(e)) });
  const comment = useMutation({ mutationFn: () => api(`/tasks/${task.id}/comments`, { method: "POST", body: { body, internal } }),
    onSuccess: () => { setBody(""); qc.invalidateQueries({ queryKey: ["task-comments", task.id] }); onChange(); }, onError: (e) => toast.error(errorMessage(e)) });
  const dep = useMutation({ mutationFn: (depId: string) => api(`/tasks/${task.id}/dependencies`, { method: "POST", body: { depends_on_id: depId } }),
    onSuccess: onChange, onError: (e) => toast.error(errorMessage(e)) });
  const upload = useMutation({ mutationFn: (f: File) => { const fd = new FormData(); fd.append("file", f); return api(`/tasks/${task.id}/attachments`, { method: "POST", body: fd }); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task-files", task.id] }), onError: (e) => toast.error(errorMessage(e)) });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={current.title} description={current.description || undefined} className="max-w-2xl">
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Status" htmlFor="t-status">
              <Select id="t-status" value={current.status} disabled={!write} onChange={(e) => patch.mutate({ status: e.target.value })}>
                {TASK_STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
              </Select>
            </Field>
            <Field label="Assignee" htmlFor="t-assignee">
              <Select id="t-assignee" value={current.assignee_id ?? ""} disabled={!write} onChange={(e) => patch.mutate({ assignee_id: e.target.value || null })}>
                <option value="">Unassigned</option>{staff.map((s) => <option key={s.user_id} value={s.user_id}>{s.full_name}</option>)}
              </Select>
            </Field>
            <Field label="Due date" htmlFor="t-due">
              <Input id="t-due" type="date" disabled={!write} value={current.due_date ?? ""} onChange={(e) => patch.mutate({ due_date: e.target.value || null })} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" disabled={!write} checked={current.customer_visible} onChange={(e) => patch.mutate({ customer_visible: e.target.checked })} />
            Visible to customer in their portal
          </label>
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-medium"><Link2 className="size-4" /> Depends on</p>
            <div className="flex flex-wrap gap-1.5">
              {current.depends_on.map((d: string) => { const t = all.find((x) => x.id === d); return <Badge key={d} tone={t?.status === "done" ? "success" : "warning"}>{t?.title ?? d}</Badge>; })}
              {current.depends_on.length === 0 && <span className="text-xs text-muted-foreground">No dependencies</span>}
            </div>
            {write && (
              <Select aria-label="Add dependency" value="" onChange={(e) => e.target.value && dep.mutate(e.target.value)}>
                <option value="">Add dependency…</option>
                {all.filter((t) => t.id !== task.id && !current.depends_on.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </Select>
            )}
          </div>
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-medium"><Paperclip className="size-4" /> Attachments</p>
            <ul className="space-y-1 text-sm">
              {(files.data ?? []).map((f) => (
                <li key={f.id}><button className="text-primary hover:underline cursor-pointer" onClick={() => downloadFile(`/attachments/${f.id}/download`, f.filename)}>{f.filename}</button> <span className="text-xs text-muted-foreground">{Math.ceil(f.size_bytes / 1024)} KB</span></li>
              ))}
            </ul>
            {write && <Input type="file" aria-label="Upload attachment" accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.csv,.docx" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />}
          </div>
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-medium"><MessageSquare className="size-4" /> Comments</p>
            <div className="max-h-60 space-y-2 overflow-y-auto">
              {(comments.data ?? []).map((c) => (
                <div key={c.id} className={cn("rounded-lg border p-2 text-sm", c.internal && "border-dashed bg-muted/50")}>
                  <p className="text-xs text-muted-foreground">{c.author_name} · {relativeTime(c.created_at)} {c.internal && "· internal"}</p>
                  <p className="whitespace-pre-wrap">{c.body}</p>
                </div>
              ))}
            </div>
            {write && (
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (body.trim()) comment.mutate(); }}>
                <Textarea placeholder="Write a comment…" value={body} onChange={(e) => setBody(e.target.value)} aria-label="Comment" />
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal only</label>
                  <Button size="sm" type="submit" loading={comment.isPending} disabled={!body.trim()}>Comment</Button>
                </div>
              </form>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ProjectsList({ base }: { base: "/app" | "/portal" }) {
  const q = useQuery({ queryKey: ["projects"], queryFn: () => api("/projects") });
  return (
    <QueryView q={q}>
      {(d: any) => d.items.length === 0 ? <EmptyState title="No projects yet" body="Projects are created automatically when a proposal is accepted." /> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {d.items.map((p: any) => (
            <a key={p.id} href={`${base}/projects/${p.id}`} className="rounded-xl border bg-card p-5 transition hover:border-primary/40 hover:shadow-sm">
              <div className="flex items-start justify-between gap-2"><p className="font-semibold">{p.name}</p><StatusBadge status={p.stage} /></div>
              <p className="mt-1 text-sm text-muted-foreground">{p.organisation_name}</p>
              <Progress value={p.progress} className="mt-4" />
              <p className="mt-2 text-xs text-muted-foreground">{p.progress}% · {p.tasks_done}/{p.tasks_total} tasks · target {formatDate(p.target_date)}</p>
            </a>
          ))}
        </div>
      )}
    </QueryView>
  );
}
