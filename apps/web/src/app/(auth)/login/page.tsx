"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Field, Input } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";

const schema = z.object({ email: z.string().trim().email("Enter a valid email"), password: z.string().min(1, "Password is required") });

const DEMO = [
  ["engineer@deploymind.example", "Engineer"], ["pm@deploymind.example", "Project Manager"],
  ["admin@deploymind.example", "Super Admin"], ["customer@acme-ps.example", "Customer (Acme)"],
];

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      const me = await login(v.email, v.password);
      const next = params?.get("next");
      router.push(next && next.startsWith("/") ? next : homeFor(me));
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-muted-foreground">Access the engineering dashboard or your customer portal.</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!errors.password} {...register("password")} />
        </Field>
        {error && <p className="rounded-md bg-danger/10 p-3 text-sm text-danger" role="alert">{error}</p>}
        <Button type="submit" className="w-full" loading={isSubmitting}>Sign in</Button>
      </form>
      <p className="text-sm text-muted-foreground">New to DeployMind? <Link href="/register" className="font-medium text-primary hover:underline">Create an organisation account</Link></p>
      <div className="rounded-lg border border-dashed p-4">
        <p className="text-xs font-medium text-muted-foreground">Development demo accounts · password <code>DeployMind-demo-2026</code></p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {DEMO.map(([email, label]) => (
            <button key={email} type="button" className="rounded-md border px-2 py-1 text-xs hover:bg-muted cursor-pointer"
              onClick={() => { setValue("email", email); setValue("password", "DeployMind-demo-2026"); }}>{label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
