# ADR 0004: Shared-schema multi-tenancy with a provider organisation

* Status: accepted
* Date: 2026-10-30

## Context
DeployMind staff work across many customers. Customers must only ever see their own data.

## Decision
* Shared schema. Every tenant-owned table has a non-null `organisation_id`.
* A special **provider** organisation holds staff memberships. Staff act across tenants within their role's
  permissions. Customer memberships grant access only to their organisation, and `CUSTOMER_FORBIDDEN` removes
  internal permissions.
* All access goes through `Principal.scope_filter` and `get_scoped`. Out-of-scope ids return **404**.
* Isolation is tested exhaustively (`test_tenant_isolation.py`) and in the browser (Playwright).

## Consequences
* Simple operations and migrations. Risk is concentrated in the scoping helpers, which are small and heavily tested.
* For customers that need physical isolation, the same code can run per-tenant deployments (one database per
  environment via Terraform). PostgreSQL row-level security is a possible defence-in-depth addition.
