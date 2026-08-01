# Nel Project

## Project Brief

Nel is a local-first persistent digital personality and personal autonomous
agent being developed for Ömər. The immediate objective is not public
distribution. It is to build a system Ömər voluntarily uses and trusts over
time.

## Primary Outcome

Nel should become a reliable long-term digital companion with durable memory,
a consistent artificial identity, controlled initiative, and the ability to
reason without automatic agreement or fabricated personal history.

Nel's intended final primary interface is a small physical desktop companion
device, likely housed in a custom 3D-printed enclosure. The device is expected
to provide a screen for Nel's face, expressions, animations, and status;
microphone input; speaker output and sound effects; camera input; and either
an onboard computer or a client connection to Nel Core. Physical movement and
motors are optional, not core product requirements.

## Primary User

Ömər is the sole intended user during the current phase. Multi-user product
requirements must not shape the architecture prematurely.

A public product may be considered only after sustained personal use proves
that Nel remains useful beyond novelty.

## First Stable Version

The first stable Nel must:

- start and stop reliably;
- converse naturally in Azerbaijani;
- store and update validated user facts;
- retrieve relevant memories without sending all history to the model;
- distinguish user identity from Nel identity;
- maintain persistent Nel-owned state;
- initiate interaction under controlled conditions;
- remain silent when appropriate;
- survive provider and network failures gracefully;
- protect private data;
- have automated tests for critical behavior;
- avoid demo-specific logic and fabricated identity.

## Current Scope

- Python orchestration
- Provider-independent text and structured generation
- Validated user knowledge
- Separate Nel-owned state and identity direction
- Memory retrieval and conflict handling
- Controlled clock/event-driven reflection
- Reliability, privacy, testing, and architecture documentation
- CLI as a temporary development shell
- Platform-independent Nel Core behavior that can later serve multiple
  interface clients

## Explicitly Deferred

- unrestricted web browsing;
- phone or risky account control;
- implementation of the physical companion device before core reliability;
- unrestricted self-modification;
- public multi-user support;
- plugin marketplace;
- commercial deployment;
- voice, vision, desktop avatar, and desktop control before core reliability;
- a generic Nel framework or CLI product.

## Product Constraints

- Local-first does not mean local-only.
- Cloud inference requires explicit configuration.
- Provider replacement must preserve identity and memory.
- Interface work follows core behavior reliability.
- The physical desktop companion is the intended long-term primary interface,
  but it does not change current roadmap priorities.
- Nel Core must remain usable by the development CLI and future desktop,
  mobile, and physical-device clients.
- Hardware abstractions must not be designed before a physical prototype
  provides concrete requirements.
- Reliability and clarity take priority over feature count.
- No completion dates are promised without evidence.

## Success Measures

Public distribution should not be considered until:

- Ömər voluntarily uses Nel regularly;
- usefulness persists beyond initial novelty;
- memory is accurate enough to trust;
- fabricated facts or identity are uncommon;
- autonomous behavior is useful rather than annoying;
- long-running operation does not corrupt data or consume uncontrolled
  resources;
- a provider can be replaced without resetting Nel.

## Product Risks

| Risk | Consequence | Direction |
|---|---|---|
| Model output becomes identity | Inconsistent or fabricated Nel | Treat output as temporary until validated and stored |
| Incorrect memory | Loss of trust | Structured validation, correction, history, tests |
| Excessive autonomy | Annoyance or unsafe action | Permission boundaries and silence |
| Provider dependence | Identity loss or lock-in | Stable provider interface and durable local state |
| Premature interfaces | Attractive but unreliable product | Defer until core exit criteria pass |
| Premature framework design | Product loses focus | Optimize for Nel and Ömər first |

## Product Choices Still Open

These require Ömər's decision when they become actionable:

1. What quiet hours, interruption frequency, and user controls should govern
   proactive interaction?
2. Which categories of private context may be sent to explicitly configured
   cloud providers, and which must always remain local?
3. What user-facing controls are required for inspecting, correcting,
   forgetting, and restoring memory history?
4. Should Nel communicate only in Azerbaijani by default, or switch languages
   when Ömər does?
5. What boundaries should govern emotionally intense or relationship-like
   language while preserving honesty about Nel's artificial nature?

All other undefined technical details should use the simplest reversible
implementation and be marked provisional.
