/**
 * Domain constants shared by the web app. They mirror the backend's deterministic workflow definitions
 * (apps/api/app/domain/workflow.py); the backend remains the source of truth and enforces every rule.
 */

export const LEAD_PIPELINE = ["new", "qualified", "discovery", "assessment", "proposal", "approved", "implementation", "completed"] as const;
export const PROJECT_STAGES = ["discovery", "solution_design", "development", "integration", "testing", "deployment", "production", "handover"] as const;
export const TASK_STATUSES = ["backlog", "todo", "in_progress", "review", "done"] as const;
export const INCIDENT_STATUSES = ["open", "investigating", "identified", "resolved", "closed"] as const;
export const INCIDENT_FLOW: Record<string, string[]> = {
  open: ["investigating", "resolved"],
  investigating: ["identified", "resolved"],
  identified: ["investigating", "resolved"],
  resolved: ["closed", "investigating"],
  closed: [],
};
export const TICKET_FLOW: Record<string, string[]> = {
  open: ["in_progress", "waiting_on_customer", "resolved", "closed"],
  in_progress: ["waiting_on_customer", "resolved", "open"],
  waiting_on_customer: ["in_progress", "resolved", "closed"],
  resolved: ["closed", "in_progress"],
  closed: [],
};
export const PROPOSAL_FLOW: Record<string, string[]> = {
  draft: ["in_review"],
  in_review: ["draft", "approved"],
  approved: ["draft", "sent"],
  sent: [],
  rejected: [],
  accepted: [],
};
export const SEVERITIES = { sev1: "Critical", sev2: "Major", sev3: "Minor", sev4: "Low" } as const;
export const ROLES = {
  super_admin: "Super Admin",
  org_admin: "Organisation Admin",
  project_manager: "Project Manager",
  engineer: "Engineer",
  customer: "Customer",
  viewer: "Viewer",
} as const;

export type LeadStatus = (typeof LEAD_PIPELINE)[number] | "lost";
export type ProjectStage = (typeof PROJECT_STAGES)[number];

export const label = (s: string | null | undefined): string =>
  (s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
