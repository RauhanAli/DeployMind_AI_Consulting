# ADR 0002: Deterministic core, LLMs at the edges

* Status: accepted
* Date: 2026-10-30

## Context
Customers make spending and risk decisions from readiness scores, opportunity rankings and proposal estimates.
LLM outputs are non-deterministic, hard to audit and susceptible to prompt injection.

## Decision
* Scores (weighted question bank), opportunity priority (configurable weighted formula), proposal estimates
  (rate card), SLA deadlines, cost calculations, permissions and state machines are **plain, unit-tested code**.
* Agents receive those results as input and only **explain or draft**. Validators reject outputs that restate
  numbers inconsistently (e.g. a different score in the executive summary).
* All AI artefacts are drafts that need human approval: requirements, architecture review, proposal approval by a
  different reviewer, advisory incident analysis.
* Agents use deterministic tool plans and an allowlist. Models never pick tools.

## Consequences
* Results are reproducible and explainable ("How this was scored" shows weight × score per answer).
* Changing scoring needs a new question-bank version, which keeps historic assessments reproducible.
* Agents are less "autonomous" than a free-form tool-calling design. That's intentional for enterprise trust.
