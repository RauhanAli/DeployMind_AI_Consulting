"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ErrorState, Loading } from "@/components/app/common";
import { api } from "@/lib/api";

export default function NewAssessment() {
  const router = useRouter();
  const started = useRef(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const existing = await api("/assessments?status=draft");
        const a = existing.items[0] ?? (await api("/assessments", { method: "POST", body: {} }));
        router.replace(`/portal/assessments/${a.id}`);
      } catch (e) {
        setError(e);
      }
    })();
  }, [router]);
  return error ? <ErrorState error={error} /> : <Loading rows={4} />;
}
