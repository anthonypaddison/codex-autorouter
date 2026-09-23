# Product-building routing

Route each work unit independently. Do not assign one model to an entire product merely because one area is consequential.

| Area or stage | Default | Raise the route when |
|---|---|---|
| Discovery and user research | GPT-6 Sol High | Cross-product synthesis or a consequential bet needs Sol Medium/High according to difficulty |
| Strategy, prioritization, MVP, pricing | Sol Medium | Deep analysis of an expensive decision needs Sol High |
| Requirements and acceptance criteria | GPT-6 Sol Medium | Stakeholders, states, or edge cases are unclear: Sol High |
| UX, flows, information architecture | GPT-6 Sol High | Cross-product or consequential workflow ownership needs Sol Medium/High according to difficulty |
| Approved UI and frontend implementation | GPT-6 Sol Medium | Hydration, offline state, subtle interaction, or performance dominates: Sol High |
| Backend and APIs | GPT-6 Sol Medium | Concurrency, idempotency, authorization, or distributed boundaries dominate: Sol High |
| Databases and data models | GPT-6 Sol Medium | Online migration, locking, backfill, or rollback complexity: Sol High |
| Mobile | GPT-6 Sol Medium | Offline sync, lifecycle, background work, stores, or cross-platform architecture: Sol High |
| AI prompts and evals | GPT-6 Sol Medium | Retrieval, tool use, eval ambiguity, or safety: Sol High; system architecture: Sol High |
| Third-party integrations | GPT-6 Sol Medium | OAuth, retries, webhooks, vendor inconsistency, identity, or money movement: Sol High when difficulty warrants it |
| Payments and billing changes | GPT-6 Sol Medium | Proration, ledgers, reconciliation, refunds, entitlements, fraud, authorization, or compliance: Sol High when especially difficult |
| QA and test generation | Luna Low for complete repeated cases; otherwise Sol Medium | Flaky/CI-only or unclear coverage: Sol High; release ownership: Sol High when consequential |
| Analytics instrumentation | Luna Low for exact repeated event insertion; otherwise Sol Medium | Attribution or identity ambiguity: Sol High |
| Data and funnel analysis | GPT-6 Sol Medium | Causal ambiguity or conflicting metrics: Sol High; consequential decision: Sol High |
| Growth experiments | GPT-6 Sol High | Pricing, brand, platform, or large-spend decision: Sol High |
| Accessibility | Luna Low for exact repeated fixes; otherwise Sol Medium | Complex assistive interaction: Sol High; legal judgment: Sol High |
| Localization | Luna Low for exact catalog transformations; otherwise Sol Medium | RTL or locale architecture: Sol High |
| DevOps and CI | GPT-6 Sol Medium | Environment drift or flaky pipelines: Sol High; deployment architecture: Sol High |
| Reliability and observability | GPT-6 Sol High | SLO architecture, incidents, or cascading failure ownership: Sol High |
| Security and privacy | GPT-6 Sol High for bounded mapping | Sensitive changes: Sol High; difficult adversarial analysis: Sol xHigh only under approved deep/high policy |
| Launch readiness | GPT-6 Sol High | Cross-system go/no-go ownership or difficult failure-mode analysis: Sol High/xHigh only when justified |
| Maintenance and dependencies | Luna Low for exact repeated bumps; otherwise Sol Medium | Breaking upgrades: Sol High; framework migration: Sol High |
| Incidents | Sol Medium for diagnosis and mitigation ownership | Difficult security or customer-data incident: Sol High |

Use GPT-6 Luna Low only when the rule is complete and objective verification is cheap. GPT-6 Sol Medium is Balanced; Sol High is the High profile. Raise capability for task complexity or consequence, not merely user-intent ambiguity.

Keep work in `current` when the active root already meets the table's model and effort and delegation adds no useful parallelism, evidence gathering, or volume benefit. In Max Quality, reserve Sol xHigh for the hardest security/code-review, deep-research, critical-change, or challenging coding work; do not apply it to an entire product area by default. For mobile sync, use Sol High for one feature's bounded offline/lifecycle design; use Sol Medium/High when the task owns shared-data, cross-platform, migration, or distributed sync architecture. For design and strategy outputs, verify traceability, state/scenario coverage, assumptions, contradictions, decision criteria, and rollback or experiment guardrails rather than pretending a code test proves the artifact.

No product area or lifecycle stage selects GPT-6 Astra by itself. Astra requires an explicit user request, or an authoritative attested Sol `ROUTE_UP` to Astra Medium after the Sol child proves a capability limit. Generic severity and Max Quality remain Sol-bounded.
