import type { Metadata } from "next";

import { ServicePage } from "@/components/site/service-page";
import { SERVICES } from "@/lib/content";

const s = SERVICES.find((x) => x.slug === "prototype-to-production")!;
export const metadata: Metadata = { title: s.name, description: s.short };

export default function PrototypeToProductionPage() {
  return <ServicePage slug="prototype-to-production" />;
}
