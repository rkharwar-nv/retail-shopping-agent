// NVIDIA Retail Shopping Agent — chat UI client logic.
// Vanilla JS: fetch + EventSource + DOM. No bundler, no framework.

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ─── state ────────────────────────────────────────────────
  const state = {
    sessionId: null,
    image: null,                // {base64, mime_type, name, size}
    sse: null,                  // EventSource
    lastTurnId: null,
    activeRoles: new Set(),
    submitting: false,
  };

  // ─── small utils ──────────────────────────────────────────
  function uuid() {
    const rid =
      crypto?.randomUUID?.() ||
      (Date.now().toString(16) + Math.random().toString(16).slice(2, 10));
    return "sess-" + rid.replaceAll("-", "").slice(0, 8);
  }

  function setStatus(text, cls = "") {
    const s = $("status");
    s.textContent = text;
    s.className = "status" + (cls ? " " + cls : "");
  }

  function fmtBytes(n) {
    if (!n && n !== 0) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  function fmtMs(ms) {
    if (ms === null || ms === undefined) return "—";
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
  }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") e.className = v;
        else if (k === "html") e.innerHTML = v;
        else if (k === "text") e.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") {
          e.addEventListener(k.slice(2).toLowerCase(), v);
        } else {
          e.setAttribute(k, v);
        }
      }
    }
    if (children) {
      for (const c of [].concat(children)) {
        if (c === null || c === undefined || c === false) continue;
        e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      }
    }
    return e;
  }

  // syntax-highlight a JSON string
  function jsonHighlight(jsonStr) {
    return esc(jsonStr).replace(
      /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false)\b|\b(null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
      (m, str, colon, bool, nul, num) => {
        if (str) {
          return colon
            ? `<span class="tok-key">${str}</span>${colon}`
            : `<span class="tok-str">${str}</span>`;
        }
        if (bool) return `<span class="tok-bool">${bool}</span>`;
        if (nul) return `<span class="tok-null">${nul}</span>`;
        if (num) return `<span class="tok-num">${num}</span>`;
        return m;
      }
    );
  }

  function rawJsonBlock(obj) {
    const d = el("details", { class: "raw-toggle" });
    d.appendChild(el("summary", { text: "Raw JSON ▾" }));
    const pre = el("pre");
    pre.innerHTML = jsonHighlight(JSON.stringify(obj, null, 2));
    d.appendChild(pre);
    return d;
  }

  // ─── fixture dropdown ─────────────────────────────────────
  async function loadFixtureList() {
    const sel = $("fixture-select");
    try {
      const r = await fetch("/fixtures/list");
      if (r.status === 404) {
        // debug off — hide the fixture control entirely
        sel.disabled = true;
        const ctrl = sel.closest(".control");
        if (ctrl) ctrl.hidden = true;
        return;
      }
      if (!r.ok) return;
      const data = await r.json();
      const fixtures = data.fixtures || {};
      let count = 0;
      for (const [ptype, items] of Object.entries(fixtures)) {
        if (!items || !items.length) continue;
        const group = el("optgroup", { label: ptype });
        for (const item of items) {
          const opt = el("option", {
            value: `${ptype}/${item.name}`,
            text: `${item.name} (${fmtBytes(item.size_bytes)})`,
          });
          if (item.default_prompt) {
            opt.dataset.defaultPrompt = item.default_prompt;
          }
          group.appendChild(opt);
          count++;
        }
        sel.appendChild(group);
      }
      if (!count) {
        sel.disabled = true;
      }
    } catch (e) {
      console.warn("fixture list failed:", e);
    }
  }

  async function selectFixture(value) {
    if (!value) return;
    const [ptype, name] = value.split("/", 2);
    setStatus(`loading fixture ${name}…`, "working");
    try {
      const r = await fetch(
        `/fixtures/load/${encodeURIComponent(ptype)}/${encodeURIComponent(name)}`
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      state.image = {
        base64: data.base64,
        mime_type: data.mime_type,
        name: data.name,
        size: data.size_bytes,
      };
      showPreview();
      const sel = $("fixture-select");
      const opt = sel.selectedOptions[0];
      const dp = opt?.dataset?.defaultPrompt;
      if (dp && !$("prompt-input").value.trim()) {
        $("prompt-input").value = dp;
        autoResize();
      }
      setStatus(`fixture loaded · ${name}`, "ok");
    } catch (e) {
      setStatus(`fixture load failed: ${e.message}`, "error");
    }
  }

  // ─── image attachment ─────────────────────────────────────
  function showPreview() {
    if (!state.image) return;
    const url = `data:${state.image.mime_type};base64,${state.image.base64}`;
    $("preview-img").src = url;
    $("preview-name").textContent =
      `${state.image.name} · ${fmtBytes(state.image.size)}`;
    $("composer-preview").hidden = false;
  }

  function clearPreview() {
    state.image = null;
    $("preview-img").removeAttribute("src");
    $("preview-name").textContent = "";
    $("composer-preview").hidden = true;
    $("file-input").value = "";
  }

  function readFile(file) {
    if (!file) return;
    if (!file.type || !file.type.startsWith("image/")) {
      setStatus(`not an image: ${file.type || "unknown"}`, "error");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = String(e.target.result || "");
      const b64 = dataUrl.split(",", 2)[1] || "";
      state.image = {
        base64: b64,
        mime_type: file.type || "image/jpeg",
        name: file.name || "pasted-image",
        size: file.size || b64.length,
      };
      $("fixture-select").value = "";
      showPreview();
      setStatus(`image attached · ${state.image.name}`, "ok");
    };
    reader.onerror = () => setStatus("file read failed", "error");
    reader.readAsDataURL(file);
  }

  // ─── composer (textarea autosize, enter, paste, drag) ─────
  function autoResize() {
    const ta = $("prompt-input");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }

  // ─── messages list ────────────────────────────────────────
  function hideEmptyState() {
    const e = $("empty-state");
    if (e) e.style.display = "none";
  }

  function appendMessage(node) {
    hideEmptyState();
    const msgs = $("messages");
    msgs.appendChild(node);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function renderUserMessage(text, image) {
    const card = el("div", { class: "msg-card" });
    if (image) {
      const img = el("img", {
        class: "msg-thumb",
        src: `data:${image.mime_type};base64,${image.base64}`,
        alt: image.name || "attachment",
      });
      card.appendChild(img);
    }
    if (text) {
      card.appendChild(el("div", { class: "msg-text", text }));
    }
    const wrap = el("div", { class: "msg msg-user" }, [card]);
    appendMessage(wrap);
  }

  function renderAgentError(status, text) {
    const card = el("div", { class: "msg-card" });
    card.appendChild(el("div", {
      class: "msg-role-tag",
      text: status ? `ERROR · HTTP ${status}` : "ERROR",
    }));
    card.appendChild(el("div", {
      class: "msg-text",
      text: text || "request failed",
    }));
    const wrap = el("div", { class: "msg msg-agent msg-error" }, [card]);
    appendMessage(wrap);
  }

  function renderAgentMessage(understanding) {
    const u = understanding || {};
    const ptype = u.perception_type || "unknown";
    const card = el("div", { class: "msg-card" });
    card.appendChild(el("div", {
      class: "msg-role-tag",
      text: "ROLE 1 · OMNI",
    }));

    // header pill row
    const head = el("div", { class: "card-head" });
    head.appendChild(el("span", {
      class: "ptype-pill",
      text: ptype.replace("_", " "),
    }));
    if (u.perception_confidence !== null && u.perception_confidence !== undefined) {
      head.appendChild(el("span", {
        class: "conf-pill",
        text: `confidence ${Number(u.perception_confidence).toFixed(2)}`,
      }));
    }
    card.appendChild(head);

    if (u.scene_summary) {
      card.appendChild(el("div", { class: "scene-summary", text: u.scene_summary }));
    }
    if (u.user_intent_hint) {
      card.appendChild(el("div", { class: "intent-hint", text: `Intent: ${u.user_intent_hint}` }));
    }

    const renderer = RENDERERS[ptype] || RENDERERS.unknown;
    const body = renderer(u);
    if (body) card.appendChild(body);

    card.appendChild(rawJsonBlock(u));

    const wrap = el("div", { class: "msg msg-agent" }, [card]);
    appendMessage(wrap);
  }

  // ─── per-perception renderers ─────────────────────────────
  const RENDERERS = {
    pantry: renderPantry,
    shopping_list: renderShoppingList,
    food_label: renderFoodLabel,
    fashion: renderFashion,
    cosmetics: renderCosmetics,
    unknown: renderUnknown,
  };

  function sectionLabel(text) {
    return el("div", { class: "section-label", text });
  }

  function renderPantry(u) {
    const p = u.pantry || {};
    const frag = document.createDocumentFragment();
    const items = p.items || [];
    if (items.length) {
      frag.appendChild(sectionLabel(`Items observed (${items.length})`));
      const grid = el("div", { class: "items-grid" });
      for (const it of items) {
        const card = el("div", { class: "item-card" });
        card.appendChild(el("div", { class: "item-name", text: it.name || "?" }));
        const meta = [];
        if (it.quantity_hint) meta.push(it.quantity_hint);
        if (it.brand) meta.push(it.brand);
        if (meta.length) {
          card.appendChild(el("div", { class: "item-meta", text: meta.join(" · ") }));
        }
        if (it.freshness_hint) {
          card.appendChild(el("span", { class: "item-tag", text: it.freshness_hint }));
        }
        if (it.category) {
          card.appendChild(el("span", { class: "item-tag", text: it.category }));
        }
        grid.appendChild(card);
      }
      frag.appendChild(grid);
    }

    if (p.overall_coverage) {
      frag.appendChild(sectionLabel("Overall coverage"));
      frag.appendChild(el("div", { class: "msg-text", text: p.overall_coverage }));
    }

    const gaps = p.notable_gaps || [];
    if (gaps.length) {
      frag.appendChild(sectionLabel("Notable gaps"));
      const ul = el("ul", { class: "bullet-list" });
      for (const g of gaps) ul.appendChild(el("li", { text: g }));
      frag.appendChild(ul);
    }

    const hints = p.suggested_recipe_hints || [];
    if (hints.length) {
      frag.appendChild(sectionLabel("Suggested uses"));
      const ul = el("ul", { class: "bullet-list" });
      for (const h of hints) ul.appendChild(el("li", { text: h }));
      frag.appendChild(ul);
    }

    if (!items.length && !gaps.length && !hints.length && !p.overall_coverage) {
      frag.appendChild(el("div", { class: "act-empty", text: "no pantry details extracted" }));
    }
    return frag;
  }

  function renderShoppingList(u) {
    const s = u.shopping_list || {};
    const frag = document.createDocumentFragment();
    const items = s.items || [];
    if (items.length) {
      frag.appendChild(sectionLabel(`Transcribed lines (${items.length})`));
      const ul = el("ul", { class: "bullet-list" });
      for (const it of items) {
        const label = [
          it.normalized_name || it.raw_text || "—",
          it.quantity ? `(${it.quantity})` : "",
          it.category_hint ? `· ${it.category_hint}` : "",
        ].filter(Boolean).join(" ");
        ul.appendChild(el("li", { text: label }));
      }
      frag.appendChild(ul);
    }

    const amb = s.ambiguous_lines || [];
    if (amb.length) {
      const c = el("div", { class: "callout callout-amber" });
      c.appendChild(el("div", { class: "callout-title", text: "Flagged · ambiguous" }));
      const ul = el("ul", { class: "bullet-list" });
      for (const a of amb) ul.appendChild(el("li", { text: a }));
      c.appendChild(ul);
      frag.appendChild(c);
    }

    if (s.legibility_score !== null && s.legibility_score !== undefined) {
      frag.appendChild(sectionLabel("Legibility"));
      frag.appendChild(el("div", { class: "msg-text",
        text: `${(Number(s.legibility_score) * 100).toFixed(0)}%` }));
    }

    if (!items.length && !amb.length) {
      frag.appendChild(el("div", { class: "act-empty", text: "no list items extracted" }));
    }
    return frag;
  }

  function renderFoodLabel(u) {
    const f = u.food_label || {};
    const frag = document.createDocumentFragment();

    if (f.product_name || f.brand) {
      const head = el("div", { class: "card-head" });
      if (f.product_name) {
        head.appendChild(el("span", {
          class: "item-name",
          text: f.product_name,
        }));
      }
      if (f.brand) {
        head.appendChild(el("span", {
          class: "item-tag",
          text: f.brand,
        }));
      }
      frag.appendChild(head);
    }

    const macros = f.macros || {};
    const hasNutri =
      (f.serving_size) ||
      (f.calories_per_serving !== null && f.calories_per_serving !== undefined) ||
      Object.keys(macros).length;
    if (hasNutri) {
      frag.appendChild(sectionLabel("Nutrition facts"));
      const grid = el("div", { class: "nutri-grid" });
      grid.appendChild(el("div", {
        class: "nutri-header",
        text: f.serving_size
          ? `Serving size: ${f.serving_size}`
          : "Per serving",
      }));
      if (f.calories_per_serving !== null && f.calories_per_serving !== undefined) {
        grid.appendChild(el("div", { class: "k", text: "Calories" }));
        grid.appendChild(el("div", { class: "v", text: String(f.calories_per_serving) }));
      }
      for (const [k, v] of Object.entries(macros)) {
        grid.appendChild(el("div", { class: "k", text: k }));
        grid.appendChild(el("div", { class: "v", text: String(v) }));
      }
      frag.appendChild(grid);
    }

    const ing = f.ingredients_list || [];
    if (ing.length) {
      frag.appendChild(sectionLabel("Ingredients"));
      frag.appendChild(el("div", {
        class: "msg-text",
        text: ing.join(", "),
      }));
    }

    const allergens = f.allergen_callouts || [];
    if (allergens.length) {
      const c = el("div", { class: "callout callout-red" });
      c.appendChild(el("div", { class: "callout-title", text: "Allergens" }));
      c.appendChild(el("div", { class: "msg-text", text: allergens.join(" · ") }));
      frag.appendChild(c);
    }

    const certs = f.certifications || [];
    if (certs.length) {
      frag.appendChild(sectionLabel("Certifications"));
      const wrap = el("div", { class: "descriptors" });
      for (const c of certs) {
        wrap.appendChild(el("span", { class: "item-tag", text: c }));
      }
      frag.appendChild(wrap);
    }

    return frag;
  }

  function renderFashion(u) {
    const f = u.fashion || {};
    const frag = document.createDocumentFragment();
    const primary = f.primary_item;
    if (primary) {
      frag.appendChild(sectionLabel("Primary garment"));
      frag.appendChild(garmentAttrs(primary));
      const desc = primary.style_descriptors || [];
      if (desc.length) {
        frag.appendChild(sectionLabel("Style descriptors"));
        const wrap = el("div", { class: "descriptors" });
        for (const d of desc) wrap.appendChild(el("span", { class: "item-tag", text: d }));
        frag.appendChild(wrap);
      }
    }
    const extras = f.additional_items || [];
    if (extras.length) {
      frag.appendChild(sectionLabel(`Additional items (${extras.length})`));
      for (const it of extras) frag.appendChild(garmentAttrs(it));
    }
    if (f.occasion_hint) {
      frag.appendChild(sectionLabel("Occasion"));
      frag.appendChild(el("div", { class: "msg-text", text: f.occasion_hint }));
    }
    if (!primary && !extras.length) {
      frag.appendChild(el("div", { class: "act-empty", text: "no garments extracted" }));
    }
    return frag;
  }

  function garmentAttrs(item) {
    const list = el("div", { class: "attr-list" });
    const rows = [
      ["Type",     item.garment_type],
      ["Color",    item.color],
      ["Pattern",  item.pattern],
      ["Material", item.material_guess],
      ["Brand",    item.brand_visible],
      ["Size",     item.size_visible],
    ];
    for (const [k, v] of rows) {
      if (!v) continue;
      list.appendChild(el("div", { class: "k", text: k }));
      list.appendChild(el("div", { class: "v", text: v }));
    }
    return list;
  }

  function renderCosmetics(u) {
    const c = u.cosmetics || {};
    const frag = document.createDocumentFragment();
    const rows = [
      ["Product type", c.product_type],
      ["Brand", c.brand],
    ];
    const attrs = el("div", { class: "attr-list" });
    let any = false;
    for (const [k, v] of rows) {
      if (!v) continue;
      attrs.appendChild(el("div", { class: "k", text: k }));
      attrs.appendChild(el("div", { class: "v", text: v }));
      any = true;
    }
    if (any) {
      frag.appendChild(sectionLabel("Product identity"));
      frag.appendChild(attrs);
    }
    if (c.notes) {
      frag.appendChild(sectionLabel("Notes"));
      frag.appendChild(el("div", { class: "msg-text", text: c.notes }));
    }
    if (!any && !c.notes) {
      frag.appendChild(el("div", { class: "act-empty", text: "no cosmetics details extracted" }));
    }
    return frag;
  }

  function renderUnknown(u) {
    const frag = document.createDocumentFragment();
    const items = u.detected_items || [];
    if (items.length) {
      frag.appendChild(sectionLabel(`Detected items (${items.length})`));
      const ul = el("ul", { class: "bullet-list" });
      for (const it of items) {
        const parts = [it.name || "?"];
        if (it.source_modality) parts.push(`(${it.source_modality})`);
        if (it.confidence !== null && it.confidence !== undefined) {
          parts.push(`· ${Number(it.confidence).toFixed(2)}`);
        }
        ul.appendChild(el("li", { text: parts.join(" ") }));
      }
      frag.appendChild(ul);
    } else if (!u.scene_summary) {
      frag.appendChild(el("div", { class: "act-empty", text: "nothing detected" }));
    }
    return frag;
  }

  // ─── activity panel ───────────────────────────────────────
  function renderStats(stats) {
    if (!stats) return;
    renderTurnCalls(stats);
    renderTotals(stats);
    renderTimeline(stats);
    renderAgents(stats);
  }

  function renderTurnCalls(stats) {
    const host = $("act-turn");
    host.innerHTML = "";
    const lastTurn = state.lastTurnId;
    const timeline = stats.timeline || [];
    if (!timeline.length) {
      host.appendChild(el("div", { class: "act-empty", text: "Submit a message to see calls appear." }));
      return;
    }
    const turnIds = Array.from(new Set(timeline.map((t) => t.turn_id)));
    const targetTurn = lastTurn && turnIds.includes(lastTurn)
      ? lastTurn
      : turnIds[turnIds.length - 1];
    const turnEvents = timeline.filter((t) => t.turn_id === targetTurn);
    const calls = turnEvents.filter((t) => /\.done$|\.error$/.test(t.event || ""));
    if (!calls.length) {
      host.appendChild(el("div", { class: "act-empty", text: "turn in progress…" }));
      return;
    }
    for (const c of calls) {
      const row = el("div", { class: "act-row" });
      row.appendChild(el("span", {
        class: "label",
        text: c.event + (c.model_id ? ` · ${c.model_id.split("/").pop()}` : ""),
      }));
      row.appendChild(el("span", { class: "num", text: fmtMs(c.duration_ms) }));
      host.appendChild(row);
    }
  }

  function renderTotals(stats) {
    const host = $("act-totals");
    host.innerHTML = "";
    const cbm = stats.calls_by_model || {};
    const keys = Object.keys(cbm);
    if (!keys.length) {
      host.appendChild(el("div", { class: "act-empty", text: "No calls yet." }));
      return;
    }
    for (const k of keys) {
      const v = cbm[k];
      const row = el("div", { class: "model-row" });
      row.appendChild(el("div", { class: "model-id", text: k }));
      const metrics = el("div", { class: "metrics" });
      const mrows = [
        ["calls",     v.calls],
        ["latency",   fmtMs(v.total_latency_ms)],
        ["prompt",    v.prompt_tokens],
        ["completion", v.completion_tokens],
        ["reasoning", v.reasoning_tokens],
      ];
      for (const [k2, v2] of mrows) {
        const m = el("div", { class: "metric" });
        m.appendChild(el("span", { class: "k", text: k2 }));
        m.appendChild(el("span", { class: "v", text: String(v2) }));
        metrics.appendChild(m);
      }
      row.appendChild(metrics);
      host.appendChild(row);
    }
    const turnsRow = el("div", { class: "act-row" });
    turnsRow.appendChild(el("span", { class: "label", text: "turns" }));
    turnsRow.appendChild(el("span", { class: "num", text: String(stats.turns || 0) }));
    host.appendChild(turnsRow);
  }

  function renderTimeline(stats) {
    const host = $("act-timeline");
    host.innerHTML = "";
    const tl = stats.timeline || [];
    if (!tl.length) {
      host.appendChild(el("div", { class: "act-empty", text: "Nothing to show yet." }));
      return;
    }
    const lastTurn = state.lastTurnId || tl[tl.length - 1].turn_id;
    const rows = tl.filter((t) => t.turn_id === lastTurn);
    for (const r of rows) {
      const isErr = (r.event || "").endsWith(".error");
      const row = el("div", { class: "timeline-row" + (isErr ? " err" : "") });
      row.appendChild(el("span", { class: "t", text: `+${r.t_ms || 0}ms` }));
      row.appendChild(el("span", { class: "ev", text: r.event || "" }));
      row.appendChild(el("span", {
        class: "dur",
        text: r.duration_ms ? fmtMs(r.duration_ms) : "",
      }));
      host.appendChild(row);
    }
  }

  function renderAgents(stats) {
    const active = new Set(stats.agents_active || []);
    state.activeRoles = active;
    const slots = $("act-agents").querySelectorAll(".agent-slot");
    slots.forEach((slot, idx) => {
      const role = `role${idx + 1}`;
      // Only mark the role(s) the spec already wired; future stays future.
      if (slot.classList.contains("future")) return;
      slot.classList.toggle("active", active.has(role));
      slot.classList.toggle("idle", !active.has(role));
    });
  }

  async function loadStats() {
    if (!state.sessionId) return;
    try {
      const r = await fetch(`/sessions/${encodeURIComponent(state.sessionId)}/stats`);
      if (r.status === 404) {
        showPanelDisabled();
        return;
      }
      if (!r.ok) return;
      const stats = await r.json();
      renderStats(stats);
    } catch (e) {
      console.warn("stats fetch failed:", e);
    }
  }

  function showPanelDisabled() {
    const msg = "debug mode off — enable in config.yaml to see activity";
    for (const id of ["act-turn", "act-totals", "act-timeline", "act-subagents"]) {
      const host = $(id);
      if (host) {
        host.innerHTML = "";
        host.appendChild(el("div", { class: "act-empty", text: msg }));
      }
    }
  }

  // ─── SSE live stream ──────────────────────────────────────
  function openStream() {
    closeStream();
    if (!state.sessionId) return;
    let es;
    try {
      es = new EventSource(`/events/stream/${encodeURIComponent(state.sessionId)}`);
    } catch (e) {
      return;
    }
    state.sse = es;
    const refresh = () => loadStats();
    es.addEventListener("model.call.started", refresh);
    es.addEventListener("model.call.succeeded", refresh);
    es.addEventListener("model.call.failed", refresh);
    es.addEventListener("turn.received", refresh);
    es.addEventListener("turn.completed", refresh);
    es.onmessage = refresh;
    es.onerror = () => { /* silent degrade — keep working */ };
  }

  function closeStream() {
    if (state.sse) {
      try { state.sse.close(); } catch (e) { /* ignore */ }
      state.sse = null;
    }
  }

  // ─── trace drawer ─────────────────────────────────────────
  function openDrawer() {
    $("drawer").hidden = false;
    requestAnimationFrame(() => $("drawer").classList.add("open"));
    fetchTrace();
  }

  function closeDrawer() {
    const d = $("drawer");
    d.classList.remove("open");
    setTimeout(() => { d.hidden = true; }, 240);
  }

  async function fetchTrace() {
    const body = $("drawer-body");
    body.innerHTML = "";
    body.appendChild(el("div", { class: "act-empty", text: "loading…" }));
    if (!state.sessionId) return;
    try {
      const r = await fetch(`/debug/trace/${encodeURIComponent(state.sessionId)}`);
      if (r.status === 404) {
        body.innerHTML = "";
        body.appendChild(el("div", { class: "act-empty", text: "debug mode off" }));
        return;
      }
      if (!r.ok) {
        body.innerHTML = "";
        body.appendChild(el("div", { class: "act-empty", text: `HTTP ${r.status}` }));
        return;
      }
      const data = await r.json();
      renderTrace(data);
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(el("div", { class: "act-empty", text: `trace error: ${e.message}` }));
    }
  }

  function renderTrace(data) {
    const body = $("drawer-body");
    body.innerHTML = "";
    const entries = data.entries || [];
    if (!entries.length) {
      body.appendChild(el("div", { class: "act-empty", text: "no trace entries yet" }));
      return;
    }
    for (const e of entries.slice().reverse()) {
      body.appendChild(renderTraceEntry(e));
    }
  }

  function renderTraceEntry(entry) {
    const wrap = el("div", { class: "trace-entry" });
    const meta = el("div", { class: "trace-meta" });
    const badges = [
      entry.role !== undefined && entry.role !== null ? `role ${entry.role}` : null,
      entry.model_id || null,
      entry.duration_ms !== undefined ? `${entry.duration_ms} ms` : null,
      entry.finish_reason ? `finish ${entry.finish_reason}` : null,
    ].filter(Boolean);
    for (const b of badges) {
      meta.appendChild(el("span", { class: "trace-badge", text: b }));
    }
    wrap.appendChild(meta);

    wrap.appendChild(
      detailBlock("system_prompt_assembled",
        el("pre", { text: entry.system_prompt_assembled || "" }))
    );
    wrap.appendChild(
      detailBlock("user_message_trace",
        preJson(entry.user_message_trace))
    );

    // Redact auth headers in upstream_request
    const req = redactAuth(entry.upstream_request);
    wrap.appendChild(
      detailBlock("upstream_request", preJson(req))
    );
    wrap.appendChild(
      detailBlock("upstream_response_raw",
        el("pre", { text: entry.upstream_response_raw || "" }), true)
    );

    if (entry.usage) {
      const usage = entry.usage;
      const grid = el("div", { class: "usage-grid" });
      for (const [k, v] of Object.entries(usage)) {
        grid.appendChild(el("span", { class: "k", text: k }));
        grid.appendChild(el("span", { class: "v", text: String(v) }));
      }
      wrap.appendChild(detailBlock("usage", grid));
    }

    return wrap;
  }

  function detailBlock(title, child, openByDefault = false) {
    const d = el("details");
    if (openByDefault) d.open = true;
    d.appendChild(el("summary", { text: title }));
    d.appendChild(child);
    return d;
  }

  function preJson(obj) {
    const pre = el("pre");
    pre.innerHTML = jsonHighlight(JSON.stringify(obj, null, 2));
    return pre;
  }

  function redactAuth(req) {
    if (!req || typeof req !== "object") return req;
    const copy = JSON.parse(JSON.stringify(req));
    const walk = (o) => {
      if (!o || typeof o !== "object") return;
      for (const k of Object.keys(o)) {
        const lk = k.toLowerCase();
        if (lk === "authorization" || lk === "api-key" || lk === "x-api-key") {
          o[k] = "[redacted]";
        } else if (typeof o[k] === "object") {
          walk(o[k]);
        }
      }
    };
    walk(copy);
    return copy;
  }

  // ─── submit ───────────────────────────────────────────────
  async function submit() {
    if (state.submitting) return;
    const text = $("prompt-input").value.trim();
    const image = state.image;
    if (!text && !image) {
      setStatus("type a message or attach an image", "error");
      return;
    }

    state.submitting = true;
    $("send-btn").disabled = true;
    setStatus("calling /chat (Omni reasoning — can take 10-60s)…", "working");
    const t0 = Date.now();

    renderUserMessage(text, image);
    const submittedImage = image;
    $("prompt-input").value = "";
    autoResize();
    clearPreview();

    try {
      const payload = {
        session_id: state.sessionId,
        text: text || "",
        images: submittedImage ? [{
          kind: "base64",
          value: submittedImage.base64,
          mime_type: submittedImage.mime_type,
        }] : [],
      };
      const r = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const ms = Date.now() - t0;
      if (!r.ok) {
        const txt = await r.text();
        let detail = txt;
        try {
          const j = JSON.parse(txt);
          detail = j.detail || txt;
        } catch (_) { /* not JSON */ }
        setStatus(`HTTP ${r.status} - ${truncate(detail, 80)}`, "error");
        renderAgentError(r.status, detail);
        return;
      }
      const data = await r.json();
      state.lastTurnId = data.turn_id || null;
      renderAgentMessage(data.understanding || data);
      setStatus(`ok · ${(ms / 1000).toFixed(1)}s`, "ok");
      loadStats();
    } catch (e) {
      setStatus(`fetch error: ${e.message}`, "error");
      renderAgentError(null, e.message);
    } finally {
      state.submitting = false;
      $("send-btn").disabled = false;
    }
  }

  function truncate(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  // ─── session id ───────────────────────────────────────────
  function setSession(newId) {
    state.sessionId = newId;
    $("session-id").value = newId;
    state.lastTurnId = null;
    state.activeRoles = new Set();
    openStream();
    loadStats();
  }

  function newSession() {
    setSession(uuid());
    // clear messages
    const msgs = $("messages");
    msgs.innerHTML = "";
    const empty = el("div", {
      id: "empty-state",
      class: "empty-state",
    });
    empty.appendChild(el("div", { class: "empty-title", text: "Start a conversation" }));
    empty.appendChild(el("div", {
      class: "empty-sub",
      text: "Pick a fixture above, drop an image below, or just type a message. " +
            "The agent will analyze your input using Role 1 (Omni) and respond with a structured perception.",
    }));
    msgs.appendChild(empty);
    setStatus("new session · " + state.sessionId, "ok");
  }

  // ─── wire up ──────────────────────────────────────────────
  function wire() {
    setSession(uuid());

    $("new-session").addEventListener("click", newSession);
    $("fixture-select").addEventListener("change", (e) => selectFixture(e.target.value));

    $("attach-btn").addEventListener("click", () => $("file-input").click());
    $("file-input").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) readFile(f);
    });
    $("preview-clear").addEventListener("click", clearPreview);

    const composer = $("composer");
    composer.addEventListener("dragover", (e) => {
      e.preventDefault();
      composer.classList.add("dragover");
    });
    composer.addEventListener("dragleave", () => composer.classList.remove("dragover"));
    composer.addEventListener("drop", (e) => {
      e.preventDefault();
      composer.classList.remove("dragover");
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) readFile(f);
    });

    const ta = $("prompt-input");
    ta.addEventListener("input", autoResize);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    });
    ta.addEventListener("paste", (e) => {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      for (const it of items) {
        if (it.kind === "file") {
          const f = it.getAsFile();
          if (f && f.type && f.type.startsWith("image/")) {
            e.preventDefault();
            readFile(f);
            return;
          }
        }
      }
    });

    $("send-btn").addEventListener("click", submit);

    $("drawer-toggle").addEventListener("click", openDrawer);
    $("drawer-close").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("drawer").hidden) closeDrawer();
    });

    loadFixtureList();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
