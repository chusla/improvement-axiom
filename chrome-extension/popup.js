// Improvement Axiom — Popup script
// Tabs: Drafts (pending replies) + Settings (Supabase config)

document.addEventListener("DOMContentLoaded", async () => {
  // --- All DOM refs up front ---
  const tabs = document.querySelectorAll(".tab");
  const supabaseUrlInput = document.getElementById("supabaseUrl");
  const supabaseAnonKeyInput = document.getElementById("supabaseAnonKey");
  const saveBtn = document.getElementById("saveBtn");
  const savedMsg = document.getElementById("savedMsg");
  const statusBadge = document.getElementById("status");
  const statusText = document.getElementById("status-text");
  const draftsList = document.getElementById("draftsList");
  const draftCount = document.getElementById("draftCount");
  const refreshBtn = document.getElementById("refreshBtn");

  // --- Tab switching ---
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });

  // --- Helpers ---
  function showSaved(msg, color) {
    savedMsg.textContent = msg;
    savedMsg.style.color = color;
    savedMsg.classList.add("visible");
    setTimeout(() => savedMsg.classList.remove("visible"), 2000);
  }

  async function checkConnection({ supabaseUrl, supabaseAnonKey }) {
    try {
      const res = await fetch(
        `${supabaseUrl}/rest/v1/agent_config?select=key&limit=1`,
        { headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${supabaseAnonKey}` } }
      );
      if (res.ok) {
        statusBadge.className = "status-badge connected";
        statusText.textContent = "Connected";
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch {
      statusBadge.className = "status-badge disconnected";
      statusText.textContent = "Connection failed";
    }
  }

  // --- Drafts loading ---
  async function loadDrafts({ supabaseUrl, supabaseAnonKey }) {
    const headers = {
      apikey: supabaseAnonKey,
      Authorization: `Bearer ${supabaseAnonKey}`,
    };

    try {
      const draftsRes = await fetch(
        `${supabaseUrl}/rest/v1/draft_responses?status=eq.pending&select=*&order=created_at.desc&limit=20`,
        { headers }
      );

      if (!draftsRes.ok) throw new Error(`Drafts: HTTP ${draftsRes.status}`);
      const drafts = await draftsRes.json();

      if (!drafts || drafts.length === 0) {
        renderDrafts([], supabaseUrl, headers);
        return;
      }

      const tweetIds = [...new Set(drafts.map((d) => d.tweet_id).filter(Boolean))];
      const evalIds = [...new Set(drafts.map((d) => d.evaluation_id).filter(Boolean))];

      const tweetsMap = {};
      if (tweetIds.length > 0) {
        const tRes = await fetch(
          `${supabaseUrl}/rest/v1/ingested_tweets?id=in.(${tweetIds.join(",")})&select=id,tweet_text,author_handle,tweet_url`,
          { headers }
        );
        if (tRes.ok) {
          for (const t of await tRes.json()) tweetsMap[t.id] = t;
        }
      }

      const evalsMap = {};
      if (evalIds.length > 0) {
        const eRes = await fetch(
          `${supabaseUrl}/rest/v1/axiom_evaluations?id=in.(${evalIds.join(",")})&select=id,quadrant,quality_score,evaluation_reasoning`,
          { headers }
        );
        if (eRes.ok) {
          for (const e of await eRes.json()) evalsMap[e.id] = e;
        }
      }

      for (const draft of drafts) {
        draft._tweet = tweetsMap[draft.tweet_id] || null;
        draft._eval = evalsMap[draft.evaluation_id] || null;
      }

      renderDrafts(drafts, supabaseUrl, headers);
    } catch (err) {
      console.error("[Axiom] loadDrafts error:", err);
      draftCount.textContent = "Failed to load";
      draftsList.innerHTML = `<div class="drafts-empty">Error: ${err.message}</div>`;
    }
  }

  // --- Drafts rendering ---
  function renderDrafts(drafts, supabaseUrl, headers) {
    if (!drafts || drafts.length === 0) {
      draftCount.textContent = "No pending drafts";
      draftsList.innerHTML = '<div class="drafts-empty">Capture some tweets and drafts will appear here.</div>';
      return;
    }

    draftCount.textContent = `${drafts.length} pending draft${drafts.length > 1 ? "s" : ""}`;
    draftsList.innerHTML = "";

    for (const draft of drafts) {
      const tweet = draft._tweet || null;
      const evaluation = draft._eval || null;

      const card = document.createElement("div");
      card.className = "draft-card";

      const quadrant = evaluation?.quadrant || "Ambiguous";
      const quadrantClass = quadrant.toLowerCase().replace(/[- ]/g, "-");

      const authorHandle = tweet?.author_handle || "unknown";
      const originalText = tweet?.tweet_text || "";
      const tweetUrl = tweet?.tweet_url || "";

      card.innerHTML = `
        <div class="draft-meta">
          <span class="draft-author">@${authorHandle}</span>
          <span class="draft-quadrant ${quadrantClass}">${quadrant}</span>
        </div>
        ${originalText ? `<div class="draft-original">"${originalText.substring(0, 120)}${originalText.length > 120 ? "..." : ""}"</div>` : ""}
        <div class="draft-text">${draft.draft_text}</div>
        <div class="draft-tone">Tone: ${draft.tone || "—"} · Quality: ${evaluation?.quality_score?.toFixed(2) || "—"}</div>
        <div class="draft-actions">
          <button class="draft-btn draft-btn-copy" data-text="${encodeURIComponent(draft.draft_text)}">Copy Reply</button>
          ${tweetUrl ? `<button class="draft-btn draft-btn-open" data-url="${tweetUrl}">Open Tweet</button>` : ""}
          <button class="draft-btn draft-btn-dismiss" data-id="${draft.id}">Dismiss</button>
        </div>
      `;

      card.querySelector(".draft-btn-copy").addEventListener("click", async (e) => {
        const text = decodeURIComponent(e.target.dataset.text);
        await navigator.clipboard.writeText(text);
        e.target.textContent = "Copied!";
        setTimeout(() => { e.target.textContent = "Copy Reply"; }, 1500);
      });

      const openBtn = card.querySelector(".draft-btn-open");
      if (openBtn) {
        openBtn.addEventListener("click", (e) => {
          chrome.tabs.create({ url: e.target.dataset.url });
        });
      }

      card.querySelector(".draft-btn-dismiss").addEventListener("click", async (e) => {
        const id = e.target.dataset.id;
        await fetch(
          `${supabaseUrl}/rest/v1/draft_responses?id=eq.${id}`,
          {
            method: "PATCH",
            headers: { ...headers, "Content-Type": "application/json", Prefer: "return=minimal" },
            body: JSON.stringify({ status: "rejected" }),
          }
        );
        card.style.opacity = "0.3";
        card.style.pointerEvents = "none";
        setTimeout(() => {
          card.remove();
          const remaining = draftsList.querySelectorAll(".draft-card").length;
          draftCount.textContent = remaining > 0
            ? `${remaining} pending draft${remaining > 1 ? "s" : ""}`
            : "No pending drafts";
          if (remaining === 0) {
            draftsList.innerHTML = '<div class="drafts-empty">All caught up!</div>';
          }
        }, 300);
      });

      draftsList.appendChild(card);
    }
  }

  // --- Settings save handler ---
  saveBtn.addEventListener("click", async () => {
    const supabaseUrl = supabaseUrlInput.value.trim().replace(/\/$/, "");
    const supabaseAnonKey = supabaseAnonKeyInput.value.trim();

    if (!supabaseUrl || !supabaseAnonKey) {
      showSaved("Both fields are required.", "#ef4444");
      return;
    }

    await chrome.storage.sync.set({ supabaseUrl, supabaseAnonKey });
    showSaved("Settings saved", "#22c55e");
    await checkConnection({ supabaseUrl, supabaseAnonKey });
    await loadDrafts({ supabaseUrl, supabaseAnonKey });
  });

  // --- Refresh handler ---
  refreshBtn.addEventListener("click", async () => {
    const cfg = await chrome.storage.sync.get(["supabaseUrl", "supabaseAnonKey"]);
    if (cfg.supabaseUrl && cfg.supabaseAnonKey) {
      refreshBtn.textContent = "...";
      await loadDrafts(cfg);
      refreshBtn.textContent = "Refresh";
    }
  });

  // --- Init: load config and data ---
  const config = await chrome.storage.sync.get(["supabaseUrl", "supabaseAnonKey"]);

  if (config.supabaseUrl) supabaseUrlInput.value = config.supabaseUrl;
  if (config.supabaseAnonKey) supabaseAnonKeyInput.value = config.supabaseAnonKey;

  if (config.supabaseUrl && config.supabaseAnonKey) {
    await checkConnection(config);
    await loadDrafts(config);
  } else {
    draftCount.textContent = "Configure Supabase in Settings";
  }
});
