import type { Metadata } from "next";
import { Mail, MapPin, Clock } from "lucide-react";

import { SectionHeading } from "@/components/site/chrome";
import { ContactForm } from "@/components/site/forms";
import { Card, CardContent } from "@/components/ui";

export const metadata: Metadata = { title: "Contact" };

export default function ContactPage() {
  return (
    <section className="container-page grid gap-12 py-16 md:grid-cols-[1fr_1.2fr] md:py-20">
      <div className="space-y-6">
        <SectionHeading as="h1" eyebrow="Contact" title="Tell us what you are trying to achieve" intro="We reply within one working day." />
        <ul className="space-y-4 text-sm">
          <li className="flex gap-3"><Mail className="size-5 text-primary" /> hello@deploymind.example</li>
          <li className="flex gap-3"><MapPin className="size-5 text-primary" /> London · Remote-first</li>
          <li className="flex gap-3"><Clock className="size-5 text-primary" /> Mon–Fri, 9:00–17:30 UK time</li>
        </ul>
      </div>
      <Card><CardContent className="p-6"><ContactForm kind="contact" /></CardContent></Card>
    </section>
  );
}
