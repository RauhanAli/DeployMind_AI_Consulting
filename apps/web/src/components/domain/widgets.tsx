"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { Select } from "@/components/ui";
import { api } from "@/lib/api";

export function OrgSelect({ value, onChange, allowAll, id }: { value: string; onChange: (v: string) => void; allowAll?: boolean; id?: string }) {
  const q = useQuery({ queryKey: ["orgs"], queryFn: () => api("/organisations?page_size=100") });
  return (
    <Select id={id} aria-label="Organisation" value={value} onChange={(e) => onChange(e.target.value)} className="min-w-48">
      <option value="">{allowAll ? "All organisations" : "Select organisation…"}</option>
      {(q.data?.items ?? []).map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </Select>
  );
}

export function Mermaid({ code }: { code: string }) {
  const rid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = document.documentElement.classList.contains("dark");
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "neutral", fontFamily: "inherit" });
        await mermaid.parse(code);
        const { svg } = await mermaid.render(`m${rid}${Date.now()}`, code);
        if (!cancelled) { setSvg(svg); setError(null); }
      } catch (e) {
        if (!cancelled) setError((e as Error).message?.split("\n")[0] ?? "Invalid diagram");
      }
    })();
    return () => { cancelled = true; };
  }, [code, rid]);
  if (error) return <p className="rounded-md bg-danger/10 p-3 text-sm text-danger">Diagram error: {error}</p>;
  // SVG produced by mermaid with securityLevel "strict" (sanitised, no scripts or click handlers).
  return <div className="overflow-x-auto [&_svg]:mx-auto [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />;
}
