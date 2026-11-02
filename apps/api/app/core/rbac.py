"""Role and permission catalogue. This is the single source of truth seeded into the roles/permissions tables.

Two scopes exist:
- internal roles are held in the provider organisation (DeployMind staff). Staff act across customer tenants.
- customer roles are held in a customer organisation and only ever grant access to that organisation.
"""

PERMISSIONS: dict[str, str] = {
    "org.read": "View organisation profiles",
    "org.manage": "Create and edit organisations and memberships",
    "users.manage": "Invite users and change roles",
    "crm.read": "View CRM leads, contacts and activity",
    "crm.write": "Edit CRM leads, contacts and activity",
    "assessment.read": "View readiness assessments and reports",
    "assessment.write": "Create and complete readiness assessments",
    "opportunity.read": "View AI opportunities",
    "opportunity.write": "Generate and edit AI opportunities",
    "discovery.read": "View discovery sessions",
    "discovery.write": "Run discovery sessions",
    "requirements.approve": "Approve or reject requirements",
    "architecture.read": "View solution architecture",
    "architecture.write": "Generate and edit solution architecture",
    "architecture.review": "Mark architecture as reviewed",
    "proposal.read": "View proposals",
    "proposal.write": "Draft and edit proposals",
    "proposal.approve": "Approve proposals internally and send to customer",
    "proposal.decide": "Accept or reject proposals on behalf of a customer",
    "project.read": "View projects, milestones and tasks",
    "project.write": "Manage projects, milestones and tasks",
    "app.read": "View AI applications",
    "app.write": "Configure AI applications",
    "app.use": "Chat with deployed AI assistants",
    "document.read": "View documents",
    "document.write": "Upload and manage documents",
    "integration.read": "View integrations",
    "integration.write": "Configure integrations and credentials",
    "deployment.read": "View environments and deployments",
    "deployment.write": "Trigger deployments and rollbacks",
    "deployment.approve": "Approve production deployments",
    "monitoring.read": "View monitoring and telemetry",
    "evaluation.read": "View evaluation runs",
    "evaluation.write": "Run evaluations and manage datasets",
    "incident.read": "View incidents",
    "incident.write": "Create and manage incidents",
    "support.read": "View support tickets",
    "support.write": "Create and comment on support tickets",
    "support.manage": "Assign, prioritise and resolve support tickets",
    "cost.read": "View AI usage and costs",
    "cost.manage": "Manage budgets and model pricing",
    "audit.read": "View audit logs",
    "settings.manage": "Manage platform settings",
}

_ALL = set(PERMISSIONS)
_READ = {p for p in PERMISSIONS if p.endswith(".read")}

ROLES: dict[str, dict] = {
    "super_admin": {"name": "Super Admin", "scope": "internal", "permissions": _ALL,
                    "description": "Full control of the platform"},
    "org_admin": {"name": "Organisation Admin", "scope": "both",
                  "description": "Administers an organisation (internal: all tenants; customer: own tenant)",
                  "permissions": _ALL - {"settings.manage"}},
    "project_manager": {"name": "Project Manager", "scope": "internal",
                        "description": "Owns delivery, proposals and customer relationships",
                        "permissions": _READ | {"crm.write", "assessment.write", "opportunity.write", "discovery.write",
                                                "requirements.approve", "proposal.write", "proposal.approve",
                                                "project.write", "incident.write", "support.write", "support.manage",
                                                "app.use", "document.write", "cost.manage"}},
    "engineer": {"name": "Engineer", "scope": "internal",
                 "description": "Forward deployed engineer building and running solutions",
                 "permissions": _READ | {"crm.write", "assessment.write", "opportunity.write", "discovery.write",
                                         "requirements.approve", "architecture.write", "architecture.review",
                                         "proposal.write", "project.write", "app.write", "app.use",
                                         "document.write", "integration.write", "deployment.write",
                                         "evaluation.write", "incident.write", "support.write", "support.manage"}},
    "customer": {"name": "Customer", "scope": "customer",
                 "description": "Customer stakeholder with access to their own organisation",
                 "permissions": {"org.read", "assessment.read", "assessment.write", "opportunity.read",
                                 "proposal.read", "proposal.decide", "project.read", "app.use", "document.read",
                                 "document.write", "incident.read", "support.read", "support.write"}},
    "viewer": {"name": "Viewer", "scope": "both", "description": "Read-only access",
               "permissions": _READ - {"audit.read", "cost.read"}},
}

# Permissions a customer-scoped membership may never exercise, whatever its role says.
CUSTOMER_FORBIDDEN = {
    "org.manage", "crm.read", "crm.write", "discovery.read", "discovery.write", "requirements.approve",
    "architecture.write", "architecture.review", "proposal.write", "proposal.approve", "project.write",
    "app.write", "integration.read", "integration.write", "deployment.write", "deployment.approve",
    "evaluation.write", "incident.write", "support.manage", "cost.manage", "audit.read", "settings.manage",
}

INTERNAL_ROLES = [k for k, v in ROLES.items() if v["scope"] in ("internal", "both")]
CUSTOMER_ROLES = [k for k, v in ROLES.items() if v["scope"] in ("customer", "both")]
