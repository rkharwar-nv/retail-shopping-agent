# M4 — Specialist Registry (Spec v1)

**Lesson 1, part 3 of 3.** Platform module. Defines the
plug-in mechanism that lets a new vertical (grocery now, fashion
/ cosmetics / home later) be added without touching the platform.

## Purpose

M4 is the seam between the platform and any domain vertical. A
Specialist is an object that implements the `Specialist`
interface; M4 is the registry that holds them and routes a turn
to the right one.

Goal: adding fashion in Phase 2 means *implementing a new
Specialist and registering it*, nothing else.

## Scope

**In scope:** the Specialist interface, the registry, the
routing policy, how a turn is handed to a specialist.

**Out of scope (Phase 1):** learned routing, multi-specialist
handoff within a turn (that's Life Moments, Phase 3+),
specialist hot-reload.

## The Specialist interface (v1)

```
  Specialist {
    name:              string           # stable id: "grocery"
    display_name:      string           # user-facing: "Grocery"
    supported_blocks:  BlockType[]      # from M3 enum
    supported_actions: ActionKind[]     # from M3 enum

    # invoked once at platform startup after config load
    init(platform_services: PlatformServices) -> void

    # invoked once per turn if routed here
    handle(ctx: ReasoningContext) -> ResponseEnvelope

    # declarative hints used by the router (see §Routing)
    domain_keywords:  string[]          # "grocery", "food", "pantry", ...
    intent_patterns:  string[]          # regex or semantic hints
  }

  PlatformServices {
    gateway:       ModelGateway         # M0
    tool_registry: ToolRegistry         # M2
    events:        EventBus             # M-EVENTS
    vector_store:  VectorStore          # M6
    product_store: ProductStore         # M8
    profile_hook:  ProfileHook          # H3
    consent_hook:  ConsentHook          # H4
    guardrails:    GuardrailsHook       # H1
  }
```

`PlatformServices` is the one argument a specialist receives at
init. This is deliberate dependency injection — specialists
never reach for globals. Tests can pass a services bundle with
mocks and run a specialist end-to-end.

## The registry

```
  SpecialistRegistry {
    register(s: Specialist) -> void     # startup only, not runtime
    get(name: string) -> Specialist?
    list() -> Specialist[]
    route(ctx: ReasoningContext) -> Specialist
  }
```

Phase 1 holds exactly one specialist: `grocery`. The registry
still exists as a real module — not a shortcut — so that adding
the second specialist is a no-op change to the platform.

## Routing policy (v1)

Phase 1 routing is deliberately simple:

1. If `ctx.conversation` has a recent `active_specialist` sticky
   (within N turns), use it.
2. Else: rank registered specialists by
   `domain_keywords` / `intent_patterns` match against
   `ctx.understanding`.
3. If no match (or tie), use the default specialist from config
   (`routing.default_specialist`, Phase 1 = `grocery`).

Learned routing is deferred. The interface supports swapping the
routing function later — `route()` is a policy, not a rule.

## Lifecycle

```
  Platform startup
    ├── load config
    ├── construct M-SEC, M0, M1, M2, M3, M-EVENTS, M6, M8
    ├── construct PlatformServices
    ├── for each configured specialist:
    │     instantiate, call init(services), registry.register()
    └── begin serving turns

  Per turn
    ├── Role 1 (via M0) -> StructuredUnderstanding
    ├── registry.route(ctx) -> Specialist
    ├── specialist.handle(ctx) -> ResponseEnvelope
    │     (specialist internally uses Role 2, tools, stores)
    └── envelope -> UI; events -> M-EVENTS
```

## Events Emitted

| Event | When |
|-------|------|
| `specialist.registered` | At startup, per specialist |
| `specialist.routed` | Per turn, includes reason (`sticky` / `keyword` / `default`) |
| `specialist.handle.started` | Before `handle()` is called |
| `specialist.handle.succeeded` | `handle()` returned valid envelope |
| `specialist.handle.failed` | `handle()` raised or returned invalid envelope |

## Failure modes

| Condition | Behavior |
|-----------|----------|
| No specialists registered | Startup fails with explicit message |
| `route()` returns null | Platform fallbacks to default; emits `routing.fallback` event |
| `handle()` raises | Platform returns an `error` envelope (see M3) |
| `handle()` exceeds timeout (config) | Same as raise; specialist tagged unhealthy |
| Specialist returns envelope with mismatched `specialist` field | Platform overwrites with the routed name; logs violation |
| Two specialists register the same `name` | Startup fails |

## Configuration

```yaml
  routing:
    default_specialist: grocery
    sticky_turns: 3
    handle_timeout_seconds: 30

  specialists:
    - grocery
    # future:
    # - fashion
    # - cosmetics
    # - home
```

Order in the list is registration order, not priority. Priority
is the router's concern.

## Domain Generality Analysis

| Aspect | Grocery (now) | Fashion (check) | Cosmetics (honest) |
|--------|---------------|-----------------|--------------------|
| Specialist interface | fits | fits | fits |
| PlatformServices | all needed | same + possibly image embedding service later | same + TBD |
| Routing signals | keywords + patterns | same | same |
| Sticky behavior | 3-turn | probably same | probably same |
| Cross-specialist handoff | single-specialist turns only in Phase 1 | needed for Life Moments (Phase 3+) | needed for Life Moments (Phase 3+) |

The interface carries *no* grocery-specific fields. Fashion
plugs in by implementing `Specialist` with its own tools, prompts,
and block type extensions (M3). Nothing in M4 changes.

## Phase-1 reference implementation notes

- One specialist class per vertical, one file.
- Specialists own their prompts, their tool implementations, and
  their domain-attribute schemas. Platform owns none of that.
- The Grocery Specialist spec (Lesson 4: GS) is where grocery-
  specific content lives. M4 stays domain-agnostic forever.
- The `supported_blocks` / `supported_actions` arrays let the UI
  know what to expect from a given specialist, useful for
  future UI capability negotiation.

## Open questions

- Should `route()` be async? Phase 1 default: synchronous, fast
  local logic only. Learned / remote routing would go async.
- Do we need a "composite specialist" shape for Life Moments
  later (L2 in the PRD)? Deferred. The current interface doesn't
  preclude it — a composite is just a specialist that internally
  fans out to others.
