"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { registerSchema } from "@/lib/schemas";

import { Button, Field, Input, Select } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";



const SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5000+"];

function RegisterForm() {
  const { register: signUp } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof registerSchema>>({
    resolver: zodResolver(registerSchema), defaultValues: { company_size: "51-200" } });

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await signUp(v);
      router.push(params?.get("next") === "assessment" ? "/portal/assessments/new" : "/portal");
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Create your organisation</h1>
        <p className="text-sm text-muted-foreground">Start with the free AI readiness assessment. No credit card, no sales pressure.</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" aria-invalid={!!errors.full_name} {...register("full_name")} />
        </Field>
        <Field label="Work email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message} hint="10+ characters with a letter and a digit">
          <Input id="password" type="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register("password")} />
        </Field>
        <Field label="Organisation" htmlFor="organisation_name" error={errors.organisation_name?.message}>
          <Input id="organisation_name" autoComplete="organization" aria-invalid={!!errors.organisation_name} {...register("organisation_name")} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Industry" htmlFor="industry"><Input id="industry" {...register("industry")} /></Field>
          <Field label="Company size" htmlFor="company_size">
            <Select id="company_size" {...register("company_size")}>{SIZES.map((s) => <option key={s}>{s}</option>)}</Select>
          </Field>
        </div>
        {error && <p className="rounded-md bg-danger/10 p-3 text-sm text-danger" role="alert">{error}</p>}
        <Button type="submit" className="w-full" loading={isSubmitting}>Create account</Button>
      </form>
      <p className="text-sm text-muted-foreground">Already have an account? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link></p>
    </div>
  );
}

export default function RegisterPage() {
  return <Suspense><RegisterForm /></Suspense>;
}
