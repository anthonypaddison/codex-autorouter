# Product-building routing

Route each work unit independently. Do not assign one model to an entire product merely because one area is consequential.

| Area or stage | Default | Raise the route when |
|---|---|---|
| Discovery and user research | Terra High | Cross-product synthesis or a consequential bet needs Sol Medium |
| Strategy, prioritization, MVP, pricing | Sol Medium | Independent challenge of an expensive decision needs Sol High |
| Requirements and acceptance criteria | Terra Medium | Stakeholders, states, or edge cases are unclear: Terra High |
| UX, flows, information architecture | Terra High | Cross-product or consequential workflow ownership needs Sol Medium |
| Approved UI and frontend implementation | Terra Medium | Hydration, offline state, subtle interaction, or performance dominates: Terra High |
| Backend and APIs | Terra Medium | Concurrency, idempotency, authorization, or distributed boundaries dominate: Terra High or Sol Medium |
| Databases and data models | Terra Medium | Online migration, locking, backfill, or rollback complexity: Terra High or Sol Medium |
| Mobile | Terra Medium | Offline sync, lifecycle, background work, stores, or cross-platform architecture: Terra High or Sol Medium |
| AI prompts and evals | Terra Medium | Retrieval, tool use, eval ambiguity, or safety: Terra High; system architecture: Sol Medium |
| Third-party integrations | Terra Medium | OAuth, retries, webhooks, vendor inconsistency, identity, or money movement: Terra High or Sol Medium |
| Payments and billing changes | Sol Medium | Implementation involving proration, ledgers, reconciliation, refunds, or entitlements: Sol Medium owner → Sol High judge; review-only fraud, authorization, compliance, or approval: Sol High |
| QA and test generation | Luna Low for complete repeated cases; otherwise Terra Medium | Flaky/CI-only or unclear coverage: Terra High; release ownership: Sol Medium |
| Analytics instrumentation | Luna Low for exact repeated event insertion; otherwise Terra Medium | Attribution or identity ambiguity: Terra High |
| Data and funnel analysis | Terra Medium | Causal ambiguity or conflicting metrics: Terra High; consequential decision: Sol Medium |
| Growth experiments | Terra High | Pricing, brand, platform, or large-spend decision: Sol Medium |
| Accessibility | Luna Low for exact repeated fixes; otherwise Terra Medium | Complex assistive interaction: Terra High; legal judgment: Sol High |
| Localization | Luna Low for exact catalog transformations; otherwise Terra Medium | RTL or locale architecture: Terra High |
| DevOps and CI | Terra Medium | Environment drift or flaky pipelines: Terra High; deployment architecture: Sol Medium |
| Reliability and observability | Terra High | SLO architecture, incidents, or cascading failure ownership: Sol Medium |
| Security and privacy | Terra High for bounded mapping | Sensitive changes: Sol Medium; adversarial review or approval: Sol High |
| Launch readiness | Terra High | Cross-system go/no-go ownership: Sol Medium; independent critical gate: Sol High |
| Maintenance and dependencies | Luna Low for exact repeated bumps; otherwise Terra Medium | Breaking upgrades: Terra High; framework migration: Sol Medium |
| Incidents | Sol Medium for diagnosis and mitigation ownership | Security or customer-data incident and independent review: Sol High |

Use Luna only when the rule is complete and objective verification is cheap. Raise effort for uncertainty and edge cases. Raise the model family for capability, scope, consequence, or synthesis ownership.

Keep work in `current` when the active root already meets the table's model and effort and delegation adds no independent review, parallelism, or volume benefit. For mobile sync, use Terra High for one feature's bounded offline/lifecycle design; use Sol Medium when the task owns shared-data, cross-platform, migration, or distributed sync architecture. For design and strategy outputs, verify traceability, state/scenario coverage, assumptions, contradictions, decision criteria, and rollback or experiment guardrails rather than pretending a code test proves the artifact.
