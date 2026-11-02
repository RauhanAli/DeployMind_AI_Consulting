import type { Metadata } from "next";

import { ServicePage } from "@/components/site/service-page";
import { SERVICES } from "@/lib/content";

const s = SERVICES.find((x) => x.slug === "custom-ai-development")!;
export const metadata: Metadata = { title: s.name, description: s.short };

export default function CustomAiDevelopmentPage() {
  return <ServicePage slug="custom-ai-development" />;
}
