import Link from "next/link";

import { Logo } from "@/components/site/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-4 py-8 sm:px-10">
        <Logo />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">{children}</div>
        <p className="text-xs text-muted-foreground"><Link href="/" className="hover:underline">← Back to deploymind</Link></p>
      </div>
      <div className="hidden flex-col justify-end bg-primary p-12 text-primary-foreground lg:flex">
        <blockquote className="max-w-md space-y-4">
          <p className="text-2xl font-semibold leading-snug">“Assess, build, deploy and run — one accountable team, one platform, full visibility.”</p>
          <p className="text-primary-foreground/70">Track readiness, proposals, projects, deployments and incidents in one place.</p>
        </blockquote>
      </div>
    </div>
  );
}
