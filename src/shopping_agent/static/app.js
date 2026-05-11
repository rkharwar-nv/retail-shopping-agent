// Dev inspector — client-side logic.
// No framework; just fetch + DOM. Renders structurally from the
// /chat JSON response, so new perception types / fields show up
// automatically without UI code changes.

(() => {
  const $ = (id) => document.getElementById(id);

  // ───────────────────────── state ─────────────────────────
  const state = {
    imageBase64: null,
    imageMime: null,
    imageName: null,
    imageSize: 0,
  };

  // ─────────────────────── utilities ───────────────────────
  function uuid() {
    // Small, good-enough session id.
    return "sess-" + crypto.randomUUID().slice(0, 8);
  }

  function setStatus(text, cls = "") {
    const s = $("status");
    s.textContent = text;
    s.className = "status " + cls;
  }

  function fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  // ──────────────────── fixture dropdown ────────────────────
  async function loadFixtureList() {
    try {
      const r = await fetch("/fixtures/list");
      if (!r.ok) return; // debug disabled → 404, silently skip
      const data = await r.json();
      const sel = $("fixture-select");
      for (const [ptype, items] of Object.entries(data.fixtures || {})) {
        if (!items.length) continue;
        const group = document.createElement("optgroup");
        group.label = ptype;
        for (const item of items) {
          const opt = document.createElement("option");
          opt.value = `${ptype}/${item.name}`;
          opt.textContent = `${item.name} (${fmtBytes(item.size_bytes)})`;
          opt.dataset.defaultPrompt = item.default_prompt || "";
          group.appendChild(opt);
        }
        sel.appendChild(group);
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
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      state.imageBase64 = data.base64;
      state.imageMime = data.mime_type;
      state.imageName = data.name;
      state.imageSize = data.size_bytes;
      showPreview(`data:${data.mime_type};base64,${data.base64}`, data.name, data.size_bytes);
      // Populate default prompt if the sidecar set one.
      const opt = $("fixture-select").selectedOptions[0];
      if (opt && opt.dataset.defaultPrompt && !$("prompt").value.trim()) {
        $("prompt").value = opt.dataset.defaultPrompt;
      }
      setStatus(`fixture loaded: ${name}`, "ok");
    } catch (e) {
      setStatus(`fixture load failed: ${e.message}`, "error");
    }
  }

  // ──────────────────── image selection ────────────────────
  function showPreview(dataUrl, name, size) {
    const img = $("preview");
    img.src = dataUrl;
    img.style.display = "block";
    document.querySelector(".dz-placeholder").style.display = "none";
    $("file-meta").textContent = `${name} · ${fmtBytes(size)}`;
  }

  function handleFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      const b64 = dataUrl.split(",", 2)[1];
      state.imageBase64 = b64;
      state.imageMime = file.type || "image/jpeg";
      state.imageName = file.name;
      state.imageSize = file.size;
      // Clear any fixture selection so the user knows what's loaded.
      $("fixture-select").value = "";
      showPreview(dataUrl, file.name, file.size);
      setStatus("image loaded", "ok");
    };
    reader.readAsDataURL(file);
  }

  // ──────────────────────── submit ────────────────────────
  async function submit() {
    if (!state.imageBase64) {
      setStatus("load an image first (fixture or upload)", "error");
      return;
    }
    const prompt = $("prompt").value.trim() || "What do you see?";
    const sessionId = $("session-id").value.trim() || uuid();
    $("session-id").value = sessionId;

    $("submit-btn").disabled = true;
    setStatus("calling /chat (Omni reasoning — can take 10-60s)…", "working");
    const started = Date.now();

    try {
      const r = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          text: prompt,
          images: [{
            kind: "base64",
            value: state.imageBase64,
            mime_type: state.imageMime,
          }],
        }),
      });
      const ms = Date.now() - started;
      if (!r.ok) {
        const text = await r.text();
        setStatus(`HTTP ${r.status} in ${(ms / 1000).toFixed(1)}s`, "error");
        renderResponseError(r.status, text);
        return;
      }
      const body = await r.json();
      setStatus(`ok · ${(ms / 1000).toFixed(1)}s`, "ok");
      renderResponse(body);
      // Fetch the upstream trace alongside.
      fetchTrace(sessionId);
    } catch (e) {
      setStatus(`fetch error: ${e.message}`, "error");
      renderResponseError(null, e.message);
    } finally {
      $("submit-btn").disabled = false;
    }
  }

  // ─────────────────── response rendering ───────────────────
  function renderResponseError(status, text) {
    $("response-empty").style.display = "none";
    $("response-content").style.display = "block";
    $("ptype-badge").textContent = "error";
    $("ptype-badge").className = "ptype-badge unknown";
    $("ptype-conf").textContent = status ? `HTTP ${status}` : "";
    $("v-scene").textContent = "";
    $("v-intent").textContent = "";
    $("typed-section").innerHTML = "";
    $("detected-items").innerHTML = "";
    $("other-fields").textContent = text || "";
  }

  function renderResponse(body) {
    $("response-empty").style.display = "none";
    $("response-content").style.display = "block";

    const ptype = body.perception_type || "unknown";
    const conf = body.perception_confidence;
    $("ptype-badge").textContent = ptype;
    $("ptype-badge").className = "ptype-badge " + ptype;
    $("ptype-conf").textContent =
      conf !== null && conf !== undefined
        ? `confidence ${Number(conf).toFixed(2)}`
        : "confidence —";

    $("v-scene").textContent = body.scene_summary || "";
    $("v-scene").className = "v" + (body.scene_summary ? "" : " muted");
    $("v-intent").textContent = body.user_intent_hint || "";
    $("v-intent").className = "v" + (body.user_intent_hint ? "" : " muted");

    // Typed payload section — render whichever typed field matches
    // perception_type. Structural renderer, no schema assumptions.
    const typed = body[ptype];
    const typedEl = $("typed-section");
    typedEl.innerHTML = "";
    if (typed && typeof typed === "object") {
      const sec = document.createElement("div");
      sec.className = "typed-section";
      sec.appendChild(Object.assign(document.createElement("h3"),
        { textContent: `${ptype} payload` }));
      sec.appendChild(renderObject(typed));
      typedEl.appendChild(sec);
    }

    // Generic detected_items fallback.
    const items = body.detected_items || [];
    const ul = $("detected-items");
    ul.innerHTML = "";
    if (items.length === 0) {
      ul.innerHTML = "<li class='muted'>none</li>";
    } else {
      for (const it of items) {
        const li = document.createElement("li");
        const name = escapeHtml(it.name || "?");
        const modality = it.source_modality ? ` (${escapeHtml(it.source_modality)})` : "";
        li.innerHTML = `${name}${modality}`;
        ul.appendChild(li);
      }
    }

    // Other fields dump — catches anything the renderer didn't
    // pick up, so schema additions stay visible until we handle
    // them properly.
    const known = new Set([
      "schema_version", "perception_type", "perception_confidence",
      "scene_summary", "user_intent_hint", "transcript",
      "detected_items", "raw_model_metadata",
      "pantry", "shopping_list", "food_label", "fashion", "cosmetics",
    ]);
    const other = {};
    for (const [k, v] of Object.entries(body)) {
      if (!known.has(k)) other[k] = v;
    }
    $("other-fields").textContent = JSON.stringify(other, null, 2);
  }

  // Structural renderer for a typed payload object.
  function renderObject(obj) {
    const frag = document.createDocumentFragment();
    for (const [k, v] of Object.entries(obj)) {
      if (v === null || v === undefined) continue;
      if (Array.isArray(v)) {
        if (v.length === 0) continue;
        const h = document.createElement("div");
        h.className = "kv";
        h.innerHTML = `<span class="k">${escapeHtml(k)} (${v.length})</span><span class="v"></span>`;
        frag.appendChild(h);
        const ul = document.createElement("ul");
        for (const item of v) {
          const li = document.createElement("li");
          if (typeof item === "object") {
            li.textContent = renderInlineObject(item);
          } else {
            li.textContent = String(item);
          }
          ul.appendChild(li);
        }
        frag.appendChild(ul);
      } else if (typeof v === "object") {
        const h = document.createElement("div");
        h.className = "kv";
        h.innerHTML = `<span class="k">${escapeHtml(k)}</span><span class="v"><code>${escapeHtml(JSON.stringify(v))}</code></span>`;
        frag.appendChild(h);
      } else {
        const kv = document.createElement("div");
        kv.className = "kv";
        kv.innerHTML = `<span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span>`;
        frag.appendChild(kv);
      }
    }
    return frag;
  }

  function renderInlineObject(o) {
    // Compact inline rep for items inside arrays, e.g. pantry items.
    const parts = [];
    for (const [k, v] of Object.entries(o)) {
      if (v === null || v === undefined || v === "") continue;
      if (typeof v === "object") continue;
      parts.push(`${k}=${v}`);
    }
    return parts.join(" · ") || JSON.stringify(o);
  }

  // ─────────────────────── trace fetch ───────────────────────
  async function fetchTrace(sessionId) {
    try {
      const r = await fetch(`/debug/trace/${encodeURIComponent(sessionId)}`);
      if (!r.ok) {
        $("trace-empty").textContent = `trace unavailable (debug disabled? HTTP ${r.status})`;
        return;
      }
      const data = await r.json();
      renderTrace(data);
    } catch (e) {
      $("trace-empty").textContent = `trace fetch error: ${e.message}`;
    }
  }

  function renderTrace(data) {
    const entries = data.entries || [];
    if (entries.length === 0) {
      $("trace-empty").style.display = "block";
      $("trace-empty").textContent = "no trace entries (debug off? buffer empty?)";
      $("trace-content").style.display = "none";
      return;
    }
    $("trace-empty").style.display = "none";
    $("trace-content").style.display = "block";
    const host = $("trace-content");
    host.innerHTML = "";

    // Newest first for prominence.
    for (const entry of entries.slice().reverse()) {
      const item = document.createElement("div");
      item.className = "trace-item";
      const usage = entry.usage || {};
      const meta = document.createElement("div");
      meta.className = "trace-meta";
      meta.innerHTML = `
        <span class="badge">role ${escapeHtml(entry.role || "?")}</span>
        <span class="badge">model ${escapeHtml(entry.model_id || "?")}</span>
        <span class="badge">${entry.duration_ms || 0} ms</span>
        <span class="badge">finish ${escapeHtml(entry.finish_reason || "?")}</span>
        ${usage.prompt_tokens !== undefined
          ? `<span class="badge">${usage.prompt_tokens} prompt / ${usage.completion_tokens || 0} completion tokens</span>`
          : ""}
      `;
      item.appendChild(meta);

      item.appendChild(buildDetails("system_prompt_assembled",
        `<pre>${escapeHtml(entry.system_prompt_assembled || "")}</pre>`));
      item.appendChild(buildDetails("user_message_trace",
        `<pre>${escapeHtml(JSON.stringify(entry.user_message_trace, null, 2))}</pre>`));
      item.appendChild(buildDetails("upstream_request (kwargs, minus messages)",
        `<pre>${escapeHtml(JSON.stringify(entry.upstream_request, null, 2))}</pre>`));
      item.appendChild(buildDetails("upstream_response_raw",
        `<pre>${escapeHtml(entry.upstream_response_raw || "")}</pre>`, true));
      if (entry.usage) {
        item.appendChild(buildDetails("usage",
          `<pre>${escapeHtml(JSON.stringify(entry.usage, null, 2))}</pre>`));
      }
      host.appendChild(item);
    }
  }

  function buildDetails(title, innerHtml, openByDefault = false) {
    const d = document.createElement("details");
    if (openByDefault) d.open = true;
    const s = document.createElement("summary");
    s.textContent = title;
    d.appendChild(s);
    const body = document.createElement("div");
    body.innerHTML = innerHtml;
    d.appendChild(body);
    return d;
  }

  // ────────────────────── wire events ──────────────────────
  function wire() {
    $("session-id").value = uuid();
    $("new-session").addEventListener("click", () => {
      $("session-id").value = uuid();
    });

    $("fixture-select").addEventListener("change", (e) => {
      selectFixture(e.target.value);
    });

    const dz = $("dropzone");
    const fi = $("file-input");
    dz.addEventListener("click", () => fi.click());
    fi.addEventListener("change", (e) => handleFile(e.target.files[0]));
    dz.addEventListener("dragover", (e) => {
      e.preventDefault();
      dz.classList.add("dragover");
    });
    dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
    dz.addEventListener("drop", (e) => {
      e.preventDefault();
      dz.classList.remove("dragover");
      handleFile(e.dataTransfer.files[0]);
    });

    $("submit-btn").addEventListener("click", submit);

    loadFixtureList();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
