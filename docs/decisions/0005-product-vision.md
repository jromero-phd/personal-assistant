# ADR 0005: Product vision and what it means for the build

Status: accepted. Date: 2026-11-19.

## Context

The project began as a Phase 1 learning build. Its purpose is the product it was always shaped like.

## Vision

A conversational personal assistant that acts as the user's butler: the single interface through
which a person deals with any company or entity, replacing today's app-per-company smartphone
model. Voice is an important modality. Hardware such as AR glasses may later add a visual layer.
This is a long-horizon aim. We start small and grow it.

## Decisions

1. **Focus is product capability.** Phases keep their order for now (workflow vs agent,
   guardrails, memory, proactivity, MCP, multi-agent, reliability, portability), but each is
   justified by what the assistant needs.
2. **The core stays modality- and device-agnostic.** Text, voice and AR are adapters over one
   core (already the rule in ADR 0002). Voice and AR are not built yet.
3. **Trust is the product.** A butler that acts for you must be safe to delegate to. Approval
   gates, risk levels and audit trails are enforced in code (Phase 3), never only in prompts.
4. **Reaching "any company or entity" is an integration problem.** Phase 6 (MCP) is the likely
   mechanism for connecting to outside services. This is a hypothesis to test, not a commitment.
5. **Still mock/sandbox only.** No real credentials or money until the gates exist and are tested.

## Open questions (not decided)

- Identity and delegation: how the assistant proves it acts for the user, and what a company
  must do to accept that.
- Memory and privacy: what is stored, where, and who can read it.
- Latency and cost targets, especially for voice.
- Whether entities expose agent-facing interfaces, or the assistant must work through existing
  web and app surfaces.

## Consequences

Phase 1 work stands.
