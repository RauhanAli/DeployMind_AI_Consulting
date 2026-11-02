"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

const TOPICS = ["AI readiness", "AI strategy", "Custom AI development", "Workflow automation", "Knowledge assistant",
  "Sales and revenue", "Prototype to production", "Other"];

export const contactSchema = z.object({
  full_name: z.string().trim().min(2, "Please enter your name"),
  email: z.string().trim().email("Enter a valid work email"),
  company: z.string().trim().min(2, "Company is required"),
  job_title: z.string().trim().max(120).optional(),
  topic: z.string().min(2, "Choose a topic"),
  message: z.string().trim().max(4000).optional(),
  preferred_slot: z.string().optional(),
});
export type ContactValues = z.infer<typeof contactSchema>;

function nextWorkingDay(): string {
  const d = new Date();
  d.setDate(d.getDate() + (d.getDay() === 5 ? 3 : d.getDay() === 6 ? 2 : 1));
  d.setHours(10, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

export function ContactForm(props: { kind: "contact" | "discovery" }) {
  return <Suspense><ContactFormInner {...props} /></Suspense>;
}

function ContactFormInner({ kind }: { kind: "contact" | "discovery" }) {
  const params = useSearchParams();
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const schema = kind === "discovery"
    ? contactSchema.refine((v) => v.preferred_slot && new Date(v.preferred_slot) > new Date(), {
        path: ["preferred_slot"], message: "Choose a future date and time" })
    : contactSchema;
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<ContactValues>({
    resolver: zodResolver(schema),
    defaultValues: { topic: params?.get("topic") ?? (kind === "discovery" ? "AI readiness" : "Other"),
      preferred_slot: kind === "discovery" ? nextWorkingDay() : undefined },
  });

  const onSubmit = handleSubmit(async (v) => {
    setServerError(null);
    try {
      await api("/public/discovery-calls", {
        method: "POST",
        body: { ...v, kind, preferred_slot: new Date(v.preferred_slot || Date.now()).toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
      });
      setDone(true);
    } catch (e) {
      setServerError(errorMessage(e));
    }
  });

  if (done) {
    return (
      <div className="space-y-3 py-6 text-center" role="status">
        <CheckCircle2 className="mx-auto size-10 text-success" />
        <h2 className="text-xl font-semibold">{kind === "discovery" ? "Request received" : "Message sent"}</h2>
        <p className="text-muted-foreground">
          {kind === "discovery" ? "An engineer will confirm your slot by email within one working day." : "We will get back to you within one working day."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate aria-label={kind === "discovery" ? "Book a discovery call" : "Contact form"}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" aria-invalid={!!errors.full_name} {...register("full_name")} />
        </Field>
        <Field label="Work email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Company" htmlFor="company" error={errors.company?.message}>
          <Input id="company" autoComplete="organization" aria-invalid={!!errors.company} {...register("company")} />
        </Field>
        <Field label="Job title (optional)" htmlFor="job_title">
          <Input id="job_title" autoComplete="organization-title" {...register("job_title")} />
        </Field>
      </div>
      <Field label="Topic" htmlFor="topic" error={errors.topic?.message}>
        <Select id="topic" {...register("topic")}>{TOPICS.map((t) => <option key={t}>{t}</option>)}</Select>
      </Field>
      {kind === "discovery" && (
        <Field label="Preferred date and time" htmlFor="preferred_slot" error={errors.preferred_slot?.message} hint="Your local time zone">
          <Input id="preferred_slot" type="datetime-local" aria-invalid={!!errors.preferred_slot} {...register("preferred_slot")} />
        </Field>
      )}
      <Field label={kind === "discovery" ? "What would you like to discuss?" : "Message"} htmlFor="message">
        <Textarea id="message" rows={4} {...register("message")} />
      </Field>
      {serverError && <p className="rounded-md bg-danger/10 p-3 text-sm text-danger" role="alert">{serverError}</p>}
      <Button type="submit" className="w-full" size="lg" loading={isSubmitting}>
        {kind === "discovery" ? "Request discovery call" : "Send message"}
      </Button>
      <p className="text-xs text-muted-foreground">We use your details only to respond to this request.</p>
    </form>
  );
}
