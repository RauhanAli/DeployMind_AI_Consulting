"use client";

import { useState } from "react";

import { PageHeader } from "@/components/app/common";
import { AppPicker, ChatPanel, DocumentsPanel } from "@/components/domain/knowledge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function PortalAssistant() {
  const { can } = useAuth();
  const [appId, setAppId] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="AI knowledge assistant" description="Grounded answers from your organisation's documents, with citations." actions={<AppPicker value={appId} onChange={setAppId} />} />
      {appId && (
        <Tabs defaultValue="chat">
          <TabsList><TabsTrigger value="chat">Ask</TabsTrigger>{can("document.read") && <TabsTrigger value="docs">Documents</TabsTrigger>}</TabsList>
          <TabsContent value="chat"><ChatPanel appId={appId} /></TabsContent>
          {can("document.read") && <TabsContent value="docs"><DocumentsPanel appId={appId} canWrite={can("document.write")} internal={false} /></TabsContent>}
        </Tabs>
      )}
    </>
  );
}
