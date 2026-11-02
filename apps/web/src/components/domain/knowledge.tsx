"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, FileText, Info, Plus, RefreshCw, Send, ShieldOff, ThumbsDown, ThumbsUp, Trash2, Upload, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Table, Td, Th } from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { cn, formatDate, relativeTime } from "@/lib/utils";

type Msg = { id: string; role: string; content: string; citations: any[]; insufficient_evidence: boolean; provider?: string; model?: string;
  latency_ms?: number; input_tokens?: number; output_tokens?: number; feedback?: number | null; retrieval?: any[] };

export function ChatPanel({ appId, showDiagnostics }: { appId: string; showDiagnostics?: boolean }) {
  const qc = useQueryClient();
  const [conv, setConv] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const convs = useQuery({ queryKey: ["convs", appId], queryFn: () => api<any[]>(`/apps/${appId}/conversations`) });

  useEffect(() => {
    // Recent browsers return a Promise from scrollIntoView; never hand it to React as a cleanup.
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const open = async (id: string) => {
    setConv(id);
    try { setMessages(await api<Msg[]>(`/conversations/${id}/messages`)); } catch (e) { toast.error(errorMessage(e)); }
  };
  const ask = useMutation({
    mutationFn: (q: string) => api(`/apps/${appId}/chat`, { method: "POST", body: { question: q, conversation_id: conv } }),
    onMutate: (q) => setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content: q, citations: [], insufficient_evidence: false }]),
    onSuccess: (r) => {
      setConv(r.conversation_id);
      setMessages((m) => [...m, { ...r.message, retrieval: r.retrieval }]);
      qc.invalidateQueries({ queryKey: ["convs", appId] });
    },
    onError: (e) => { toast.error(errorMessage(e)); setMessages((m) => m.slice(0, -1)); },
  });
  const feedback = useMutation({
    mutationFn: ({ id, rating }: { id: string; rating: number }) => api(`/messages/${id}/feedback`, { method: "POST", body: { rating } }),
    onSuccess: (m) => setMessages((all) => all.map((x) => (x.id === m.id ? { ...x, feedback: m.feedback } : x))),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 2 || ask.isPending) return;
    setQuestion("");
    ask.mutate(q);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      <Card className="hidden lg:block">
        <CardContent className="space-y-1 p-2">
          <Button variant="outline" size="sm" className="mb-2 w-full" onClick={() => { setConv(null); setMessages([]); }}><Plus /> New conversation</Button>
          {(convs.data ?? []).map((c) => (
            <button key={c.id} onClick={() => open(c.id)} className={cn("block w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted cursor-pointer", conv === c.id && "bg-accent")}>
              {c.title}<span className="block text-[11px] text-muted-foreground">{relativeTime(c.updated_at)}</span>
            </button>
          ))}
          {convs.data?.length === 0 && <p className="px-2 py-4 text-xs text-muted-foreground">No conversations yet.</p>}
        </CardContent>
      </Card>
      <Card className="flex min-h-[560px] flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {messages.length === 0 && (
            <EmptyState icon={Bot} title="Ask a question about your documents"
              body="Answers are grounded in documents you are authorised to access and include citations. If the evidence is insufficient, the assistant will say so." />
          )}
          {messages.map((m) => (
            <div key={m.id} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
              <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground")}>
                {m.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
              </span>
              <div className={cn("max-w-[85%] space-y-2 rounded-xl px-4 py-3 text-sm", m.role === "user" ? "bg-primary text-primary-foreground" : "border bg-card")}>
                {m.insufficient_evidence && <Badge tone="warning"><ShieldOff className="size-3" /> Insufficient evidence</Badge>}
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                {m.citations?.length > 0 && (
                  <div className="space-y-1.5 border-t pt-2">
                    <p className="text-xs font-medium text-muted-foreground">Sources</p>
                    {m.citations.map((c) => (
                      <details key={c.index} className="rounded-md bg-muted/60 px-2 py-1 text-xs">
                        <summary className="cursor-pointer"><span className="font-semibold">[{c.index}]</span> {c.title} <span className="text-muted-foreground">· part {c.ordinal + 1}</span></summary>
                        <p className="mt-1 text-muted-foreground">{c.snippet}…</p>
                      </details>
                    ))}
                  </div>
                )}
                {m.role === "assistant" && !m.id.startsWith("tmp") && (
                  <div className="flex items-center gap-1 pt-1 text-xs text-muted-foreground">
                    <button aria-label="Helpful" onClick={() => feedback.mutate({ id: m.id, rating: 1 })} className={cn("rounded p-1 hover:bg-muted cursor-pointer", m.feedback === 1 && "text-success")}><ThumbsUp className="size-3.5" /></button>
                    <button aria-label="Not helpful" onClick={() => feedback.mutate({ id: m.id, rating: -1 })} className={cn("rounded p-1 hover:bg-muted cursor-pointer", m.feedback === -1 && "text-danger")}><ThumbsDown className="size-3.5" /></button>
                    {showDiagnostics && <span className="ml-2">{m.provider}:{m.model} · {m.latency_ms} ms · {m.input_tokens}+{m.output_tokens} tokens</span>}
                  </div>
                )}
                {showDiagnostics && m.retrieval && m.retrieval.length > 0 && (
                  <details className="text-xs"><summary className="cursor-pointer text-muted-foreground"><Info className="mr-1 inline size-3" />Retrieval diagnostics</summary>
                    <Table className="mt-1 text-[11px]"><thead><tr><Th>Chunk</Th><Th>Rel.</Th><Th>Vector</Th><Th>Keyword</Th></tr></thead><tbody>
                      {m.retrieval.map((r, i) => <tr key={i}><Td>{r.title} #{r.ordinal + 1}</Td><Td>{r.relevance}</Td><Td>{r.vector_similarity}</Td><Td>{r.keyword_rank}</Td></tr>)}
                    </tbody></Table>
                  </details>
                )}
              </div>
            </div>
          ))}
          {ask.isPending && <p className="text-sm text-muted-foreground">Searching documents…</p>}
          <div ref={endRef} />
        </div>
        <form onSubmit={submit} className="flex gap-2 border-t p-3">
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Who approves expense claims over £500?" aria-label="Question" maxLength={2000} />
          <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 2}><Send /> Ask</Button>
        </form>
      </Card>
    </div>
  );
}

export function DocumentsPanel({ appId, canWrite, internal }: { appId: string; canWrite: boolean; internal: boolean }) {
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ["docs", appId], queryFn: () => api<any[]>(`/apps/${appId}/documents`),
    refetchInterval: (q) => ((q.state.data ?? []).some((d: any) => ["uploaded", "processing"].includes(d.status)) ? 2000 : false) });
  const [visibility, setVisibility] = useState("organisation");
  const fileRef = useRef<HTMLInputElement>(null);
  const inv = () => qc.invalidateQueries({ queryKey: ["docs", appId] });
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        fd.append("visibility", visibility);
        await api(`/apps/${appId}/documents`, { method: "POST", body: fd });
      }
    },
    onSuccess: () => { toast.success("Uploaded — ingestion started"); inv(); if (fileRef.current) fileRef.current.value = ""; },
    onError: (e) => { toast.error(errorMessage(e)); inv(); },
  });
  const del = useMutation({ mutationFn: (id: string) => api(`/documents/${id}`, { method: "DELETE" }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const reprocess = useMutation({ mutationFn: (id: string) => api(`/documents/${id}/reprocess`, { method: "POST" }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const setVis = useMutation({ mutationFn: ({ id, v }: { id: string; v: string }) => api(`/documents/${id}`, { method: "PATCH", body: { visibility: v } }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div><CardTitle>Documents</CardTitle><p className="text-sm text-muted-foreground">PDF, DOCX, TXT or Markdown, up to 20 MB. Parsed, chunked and embedded into pgvector.</p></div>
        {canWrite && (
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="Visibility for new uploads" value={visibility} onChange={(e) => setVisibility(e.target.value)} className="w-44">
              <option value="organisation">Whole organisation</option>
              <option value="restricted">Restricted (only me)</option>
              {internal && <option value="internal">DeployMind staff only</option>}
            </Select>
            <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => e.target.files?.length && upload.mutate(e.target.files)} />
            <Button onClick={() => fileRef.current?.click()} loading={upload.isPending}><Upload /> Upload</Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        <QueryView q={docs}>
          {(list) => list.length === 0 ? <EmptyState icon={FileText} title="No documents yet" body="Upload policies, procedures or knowledge articles to ground the assistant." /> : (
            <Table><thead><tr><Th>Document</Th><Th>Status</Th><Th>Chunks</Th><Th>Visibility</Th><Th>Uploaded</Th><Th /></tr></thead><tbody>
              {list.map((d) => (
                <tr key={d.id}>
                  <Td><button className="text-left font-medium hover:underline cursor-pointer" onClick={() => downloadFile(`/documents/${d.id}/download`, d.filename)}>{d.title}</button>
                    <p className="text-xs text-muted-foreground">{d.filename} · {Math.ceil(d.size_bytes / 1024)} KB</p>{d.error && <p className="text-xs text-danger">{d.error}</p>}</Td>
                  <Td><StatusBadge status={d.status} /></Td><Td>{d.chunk_count}</Td>
                  <Td>{canWrite ? (
                    <Select aria-label={`Visibility of ${d.title}`} className="h-8 w-36 text-xs" value={d.visibility} onChange={(e) => setVis.mutate({ id: d.id, v: e.target.value })}>
                      <option value="organisation">Organisation</option><option value="restricted">Restricted</option>{internal && <option value="internal">Internal</option>}
                    </Select>) : <Badge>{d.visibility}</Badge>}</Td>
                  <Td className="text-xs">{formatDate(d.created_at)}</Td>
                  <Td className="whitespace-nowrap text-right">{canWrite && <>
                    <Button variant="ghost" size="icon" aria-label="Reprocess" onClick={() => reprocess.mutate(d.id)}><RefreshCw /></Button>
                    <Button variant="ghost" size="icon" aria-label="Delete" onClick={() => confirm(`Delete ${d.title}?`) && del.mutate(d.id)}><Trash2 /></Button></>}</Td>
                </tr>
              ))}
            </tbody></Table>
          )}
        </QueryView>
      </CardContent>
    </Card>
  );
}

export function AppPicker({ value, onChange }: { value: string | null; onChange: (id: string) => void }) {
  const apps = useQuery({ queryKey: ["apps"], queryFn: () => api<any[]>("/apps") });
  useEffect(() => { if (!value && apps.data?.length) onChange(apps.data[0].id); }, [apps.data, value, onChange]);
  return (
    <QueryView q={apps} rows={1}>
      {(list) => list.length === 0 ? <EmptyState icon={Bot} title="No assistant deployed yet" body="Your DeployMind team will enable your knowledge assistant here once it is ready." /> : (
        <Select aria-label="Assistant" value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="max-w-sm">
          {list.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </Select>
      )}
    </QueryView>
  );
}
