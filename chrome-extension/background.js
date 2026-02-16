// Improvement Axiom — Background service worker
// Handles context menu and coordinates between popup and content script.

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "axiom-evaluate",
    title: "Evaluate with Axiom",
    contexts: ["selection"],
    documentUrlPatterns: ["https://x.com/*", "https://twitter.com/*"],
  });
  console.log("[Axiom] Extension installed, context menu created.");
});

// Handle context menu clicks (right-click selected text)
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "axiom-evaluate") return;

  const selectedText = info.selectionText;
  if (!selectedText) return;

  const config = await chrome.storage.sync.get([
    "supabaseUrl",
    "supabaseAnonKey",
  ]);

  if (!config.supabaseUrl || !config.supabaseAnonKey) {
    chrome.action.openPopup();
    return;
  }

  try {
    const response = await fetch(
      `${config.supabaseUrl}/functions/v1/ingest-tweet`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${config.supabaseAnonKey}`,
        },
        body: JSON.stringify({
          tweet_url: tab.url || "https://x.com/unknown",
          tweet_text: selectedText,
          author_handle: null,
          author_name: null,
        }),
      }
    );

    if (response.ok) {
      chrome.tabs.sendMessage(tab.id, {
        type: "axiom-toast",
        message: "Selected text captured — evaluation in progress.",
        toastType: "success",
      });
    }
  } catch (err) {
    console.error("[Axiom] Context menu ingest failed:", err);
  }
});

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "axiom-get-config") {
    chrome.storage.sync.get(["supabaseUrl", "supabaseAnonKey"], (config) => {
      sendResponse(config);
    });
    return true; // async
  }
});
