# M3 — Response Envelope (Spec v1)

**Lesson 1, part 2 of 3.** Platform module. Defines the single
output shape every specialist must return. Consumed by the UI
(U1) and by the event bus (M-EVENTS).

## Purpose

The Response Envelope is the canonical shape of "what the agent
wants to say to the user this turn." Every specialist returns
one. The UI renders any envelope without knowing which specialist
produced it. This is what makes the UI a generic renderer rather
than a grocery-specific one.

## Scope

**In scope:** the payload shape, the enumerated content types,
envelope-level metadata, state variants (loading / empty / error).

**Out of scope (Phase 1):** visual design, rich media (video/3D),
streaming partial envelopes, localization.

## Envelope shape (v1)

```
  ResponseEnvelope {
    schema_version:  1
    session_id:      string
    turn_id:         string
    specialist:      string           # "grocery", later "fashion" etc.
    state:           "ok" | "loading" | "empty" | "error"
    blocks:          Block[]          # ordered, rendered top-to-bottom
    actions:         Action[]         # optional interactive affordances
    metadata:        EnvelopeMeta
  }

  EnvelopeMeta {
    produced_at:  iso8601
    latency_ms:   int
    model_calls:  ModelCallRef[]      # for debugging / events
    trace_id:     string
  }
```

`blocks` is the ordered content. `actions` is buttons/links the
user can click. Keeping them separate means the UI can render
actions in a standard place (footer, inline) regardless of block
content.

## Block types (v1, closed enum)

Closed enum is deliberate: adding a new block type is a versioned
change. Keeps the UI honest.

| Type | Purpose | Fashion test |
|------|---------|--------------|
| `text` | Plain prose response | ✓ any domain |
| `product_card` | One product, headline attrs | ✓ domain-tagged attrs |
| `product_list` | N product cards, ranked | ✓ |
| `comparison` | 2-N products, side-by-side attrs | ✓ |
| `recipe_card` | Recipe summary + ingredient gap | grocery-specific **[1]** |
| `gap_list` | Items missing from pantry/cart | grocery-specific **[1]** |
| `confirmation` | "Added 3 items to cart" | ✓ |
| `clarifying_question` | Disambiguation prompt | ✓ |
| `error` | User-facing apology/explanation | ✓ |

**[1]** `recipe_card` and `gap_list` are grocery-scoped in v1. When
fashion arrives, it adds its own block types (`outfit_card`,
`size_fit_note`). The renderer dispatches on `type`, so new types
don't break old ones. This is the tagged-union extension pattern.

## Block schemas

```
  Block =
    | TextBlock
    | ProductCardBlock
    | ProductListBlock
    | ComparisonBlock
    | RecipeCardBlock
    | GapListBlock
    | ConfirmationBlock
    | ClarifyingQuestionBlock
    | ErrorBlock

  TextBlock {
    type: "text"
    body: string           # markdown allowed, images disallowed
    tone: "neutral" | "success" | "warning"
  }

  ProductCardBlock {
    type: "product_card"
    product: ProductRef
    headline: string?        # "healthier swap" etc.
    reason_codes: string[]   # why this product; UI may hide
  }

  ProductListBlock {
    type: "product_list"
    title: string?
    products: ProductRef[]   # each may include its own reason_codes
  }

  ComparisonBlock {
    type: "comparison"
    products: ProductRef[]
    attributes: string[]     # which fields to show side-by-side
  }

  RecipeCardBlock {
    type: "recipe_card"
    recipe_id: string
    name: string
    servings: int
    missing_item_count: int  # for UI badge; details via gap_list
  }

  GapListBlock {
    type: "gap_list"
    items: GapItem[]
  }

  GapItem {
    needed_name: string       # "whole milk, 1 cup"
    suggested_product: ProductRef?
    fulfilled_by_pantry: bool
  }

  ConfirmationBlock {
    type: "confirmation"
    summary: string           # "Added 3 items to your cart"
    detail:  string?
  }

  ClarifyingQuestionBlock {
    type: "clarifying_question"
    question: string
    options:  string[]        # optional quick-reply chips
  }

  ErrorBlock {
    type: "error"
    user_message: string      # safe to show user
    error_code:   string      # stable machine-readable
    retryable:    bool
  }
```

`ProductRef` is defined in M8 Product Store spec (forthcoming).
Minimum fields callers can rely on: `sku`, `name`, `brand`,
`price`, `image_url`, `domain` ("grocery"), `attributes` (domain
map).

## Action schema

```
  Action {
    id:     string          # stable across renders for analytics
    label:  string          # user-visible text
    kind:   "add_to_cart" | "accept_substitution" | "open_product"
          | "pick_option"  | "cancel"             | "custom"
    payload: object         # kind-specific; validated by handler
  }
```

Action kinds are a closed enum. `custom` exists as an escape
hatch; using it in Phase 1 requires a spec amendment.

## State variants

| state | When | Required blocks |
|-------|------|-----------------|
| `ok` | Normal response | >=1 block |
| `loading` | Response pending (long tool call) | 0 blocks, UI shows spinner |
| `empty` | Query succeeded but no content | 1 `text` block explaining |
| `error` | Turn failed in a user-visible way | 1 `error` block |

`loading` envelopes are sent when a turn will take more than
~1500ms. Phase 1 may skip this — flagged in SESSION-NOTES.

## Events Emitted

| Event | When |
|-------|------|
| `envelope.produced` | Specialist returns an envelope |
| `envelope.rendered` | UI confirms render (if telemetered) |

Events carry `specialist`, `state`, `block_types` (array of
strings), `action_kinds`, `latency_ms`. Events never carry block
content text or product details.

## Failure modes

| Condition | Behavior |
|-----------|----------|
| Specialist returns invalid envelope | Platform replaces with `error` envelope; logs violation |
| Unknown block `type` at render | UI skips that block, logs to events |
| `blocks` empty with `state=ok` | Platform coerces to `state=empty` with stock text block |
| Action `kind=custom` used in Phase 1 | Hard fail with spec-violation error |

## Domain Generality Analysis

| Aspect | Grocery (now) | Fashion (check) | Cosmetics (honest) |
|--------|---------------|-----------------|--------------------|
| Envelope shape | generic | same | same |
| `blocks` enum | 9 types | adds outfit_card, size_fit | adds shade_match, regimen_step — TBD |
| `actions` enum | 6 kinds | adds try_on?, save_outfit? | TBD |
| `state` variants | 4 | same | same |
| `specialist` tag | "grocery" | "fashion" | "cosmetics" |

Extension pattern: tagged union on `Block.type`. Envelope shape
never changes; only the block vocabulary grows per domain.

## Open questions

- Do we need a separate `streaming_envelope` shape for partial
  responses, or do we only stream at the transport layer and
  deliver whole envelopes to the UI? Phase 1 default: whole
  envelopes only.
- `markdown` in TextBlock — what subset? Phase 1 default:
  bold/italic/lists/links, no images, no HTML.
