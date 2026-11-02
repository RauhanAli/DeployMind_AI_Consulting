import type { Metadata } from "next";

import { ServicePage } from "@/components/site/service-page";
import { SERVICES } from "@/lib/content";

const s = SERVICES.find((x) => x.slug === "ai-automation")!;
export const metadata: Metadata = { title: s.name, description: s.short };

export default function AiAutomationPage() {
  return <ServicePage slug="ai-automation" />;
}
