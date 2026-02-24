// Improvement Axiom — Content script for X.com / Twitter.com
// Injects an "Axiom" button into each tweet's action bar,
// plus a floating action button for tweet detail / article pages.
// Extracts tweet text, URLs, article cards, and quoted tweets.

(() => {
  "use strict";

  const AXIOM_MARKER = "data-axiom-injected";

  const AXIOM_ICON = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
    <circle cx="12" cy="12" r="3" fill="currentColor" opacity="0.6"/>
  </svg>`;

  // --- Toast notifications ---
  function showToast(message, type = "info") {
    const existing = document.querySelector(".axiom-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = `axiom-toast axiom-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add("axiom-toast-visible");
    });

    setTimeout(() => {
      toast.classList.remove("axiom-toast-visible");
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // --- Extract all URLs from an element ---
  function extractUrls(el) {
    const urls = new Set();
    if (!el) return urls;

    const links = el.querySelectorAll("a[href]");
    for (const link of links) {
      const href = link.href;
      if (href && !href.match(/^https?:\/\/(x\.com|twitter\.com)\/(hashtag|search)\//)) {
        if (href.includes("t.co/") || !href.match(/^https?:\/\/(x\.com|twitter\.com)\//)) {
          urls.add(href);
        }
      }
    }

    const text = el.innerText || "";
    const urlRegex = /https?:\/\/[^\s<>"')\]]+/g;
    let match;
    while ((match = urlRegex.exec(text)) !== null) {
      urls.add(match[0]);
    }

    return urls;
  }

  // --- Extract quoted tweet content ---
  function extractQuotedTweet(container) {
    // Strategy 1: explicit quoteTweet testid (most reliable)
    let quoteContainer = container.querySelector('[data-testid="quoteTweet"]');

    // Strategy 2: any clickable tweet card that contains tweet text.
    // X doesn't always use [data-testid="quoteTweet"] — especially in timeline view.
    // A quoted tweet card is a div[role="link"] wrapping tweet content.
    if (!quoteContainer) {
      const candidates = container.querySelectorAll('div[role="link"][tabindex="0"]');
      for (const el of candidates) {
        if (el.querySelector('[data-testid="tweetText"]')) {
          quoteContainer = el;
          break;
        }
      }
    }

    // Strategy 3: blockquote fallback
    if (!quoteContainer) {
      quoteContainer = container.querySelector('div[role="blockquote"]');
    }

    if (!quoteContainer) return null;

    const quoteTextEl = quoteContainer.querySelector('[data-testid="tweetText"]');

    // Guard: don't re-use the main tweet's own text element
    const mainTextEl = container.querySelector('[data-testid="tweetText"]');
    if (quoteTextEl && quoteTextEl === mainTextEl) return null;

    const quoteText = quoteTextEl ? quoteTextEl.innerText.trim() : "";

    let quoteAuthor = "";
    const userLinks = quoteContainer.querySelectorAll('a[href^="/"]');
    for (const link of userLinks) {
      const href = link.getAttribute("href");
      if (href && /^\/[A-Za-z0-9_]{1,15}$/.test(href)) {
        const span = link.querySelector("span");
        if (span && span.textContent.startsWith("@")) {
          quoteAuthor = span.textContent.slice(1);
          break;
        }
      }
    }

    const quoteUrls = [...extractUrls(quoteContainer)];

    if (!quoteText && quoteUrls.length === 0) return null;

    return { author: quoteAuthor, text: quoteText, urls: quoteUrls };
  }

  // --- Extract article card / link preview ---
  function extractArticleCard(container) {
    const card =
      container.querySelector('[data-testid="card.wrapper"]') ||
      container.querySelector('[data-testid="card.layoutLarge.media"]') ||
      container.querySelector('[data-testid="card.layoutSmall.media"]');

    if (!card) return null;

    const detailContainer =
      card.querySelector('[data-testid="card.layoutLarge.detail"]') ||
      card.querySelector('[data-testid="card.layoutSmall.detail"]') ||
      card.querySelector('div[data-testid$=".detail"]');

    let cardTitle = "";
    let cardDescription = "";

    if (detailContainer) {
      const spans = detailContainer.querySelectorAll("span");
      if (spans.length >= 1) cardTitle = spans[0]?.innerText?.trim() || "";
      if (spans.length >= 2) cardDescription = spans[1]?.innerText?.trim() || "";
    }

    let cardUrl = "";
    const cardLink = card.querySelector("a[href]");
    if (cardLink) cardUrl = cardLink.href;

    const domainEl = card.querySelector('span[dir="ltr"]');
    const cardDomain = domainEl ? domainEl.innerText.trim() : "";

    if (!cardUrl && !cardTitle) return null;

    return { title: cardTitle, description: cardDescription, url: cardUrl, domain: cardDomain };
  }

  // --- Extract author info from a container ---
  function extractAuthor(container) {
    let authorHandle = "";
    let authorName = "";
    const userLinks = container.querySelectorAll('a[href^="/"]');
    for (const link of userLinks) {
      const href = link.getAttribute("href");
      if (href && /^\/[A-Za-z0-9_]{1,15}$/.test(href)) {
        const span = link.querySelector("span");
        if (span) {
          const text = span.textContent || "";
          if (text.startsWith("@")) {
            authorHandle = text.slice(1);
          } else if (!authorName && text.length > 0) {
            authorName = text;
          }
        }
        if (authorHandle) break;
      }
    }
    return { authorHandle, authorName };
  }

  // --- Extract tweet text using multiple strategies ---
  function extractText(container) {
    // Strategy 1: data-testid="tweetText"
    const tweetTextEl = container.querySelector('[data-testid="tweetText"]');
    if (tweetTextEl && tweetTextEl.innerText.trim()) {
      return { text: tweetTextEl.innerText.trim(), el: tweetTextEl };
    }

    // Strategy 2: X Articles / long-form content
    const articleBody =
      container.querySelector('[data-testid="article-body"]') ||
      container.querySelector('[data-testid="richTextComponent"]');
    if (articleBody && articleBody.innerText.trim()) {
      return { text: articleBody.innerText.trim().substring(0, 3000), el: articleBody };
    }

    // Strategy 3: Look for the largest text block inside the container
    // (skip tiny elements like handles, timestamps, button labels)
    let bestText = "";
    let bestEl = null;
    const candidates = container.querySelectorAll("div[dir='auto'], div[lang], span[dir='auto']");
    for (const el of candidates) {
      const t = el.innerText?.trim() || "";
      if (t.length > bestText.length && t.length > 20) {
        // Make sure it's not inside a nav/header/action bar
        if (!el.closest('[role="group"]') && !el.closest("nav") && !el.closest("header")) {
          bestText = t;
          bestEl = el;
        }
      }
    }
    if (bestText) {
      return { text: bestText.substring(0, 3000), el: bestEl };
    }

    return { text: "", el: null };
  }

  // --- Extract image URLs from a tweet ---
  function extractImages(container) {
    const images = [];
    if (!container) return images;

    // Twitter images: data-testid="tweetPhoto" wraps the photo links
    const photoEls = container.querySelectorAll('[data-testid="tweetPhoto"] img');
    for (const img of photoEls) {
      let src = img.src || "";
      if (!src || !src.includes("pbs.twimg.com")) continue;

      // Request the largest available version
      try {
        const url = new URL(src);
        url.searchParams.set("name", "large");
        src = url.toString();
      } catch {
        // keep original if URL parsing fails
      }

      if (!images.includes(src)) {
        images.push(src);
      }
    }

    // Also catch images in quoted tweets or cards that use background-image
    const bgEls = container.querySelectorAll('[data-testid="tweetPhoto"] [style*="background-image"]');
    for (const el of bgEls) {
      const style = el.style.backgroundImage || "";
      const match = style.match(/url\("?(https:\/\/pbs\.twimg\.com[^")\s]+)"?\)/);
      if (match && !images.includes(match[1])) {
        images.push(match[1]);
      }
    }

    return images;
  }

  // --- Extract tweet data from any container (article element or page section) ---
  function extractTweetData(container) {
    const { text: tweetText, el: textEl } = extractText(container);
    const { authorHandle, authorName } = extractAuthor(container);

    // Tweet URL from timestamp link
    let tweetUrl = "";
    const timeEl = container.querySelector("time");
    if (timeEl) {
      const timeLink = timeEl.closest("a");
      if (timeLink) tweetUrl = timeLink.href;
    }
    // Fallback: use current page URL if on a detail page
    if (!tweetUrl) {
      const loc = window.location.href;
      if (loc.match(/\/(status|article|i\/web)\//) || loc.match(/\/[A-Za-z0-9_]+\/status\//)) {
        tweetUrl = loc;
      } else if (authorHandle) {
        tweetUrl = `https://x.com/${authorHandle}/status/unknown`;
      }
    }

    // Extract URLs from tweet body and the whole container
    const embeddedUrls = [...extractUrls(textEl), ...extractUrls(container)];
    // Deduplicate
    const uniqueUrls = [...new Set(embeddedUrls)];

    // Quoted tweet
    const quotedTweet = extractQuotedTweet(container);

    // Article card
    const articleCard = extractArticleCard(container);

    // Images
    const mediaUrls = extractImages(container);

    // Merge URLs
    if (articleCard?.url && !uniqueUrls.includes(articleCard.url)) {
      uniqueUrls.push(articleCard.url);
    }
    if (quotedTweet?.urls) {
      for (const u of quotedTweet.urls) {
        if (!uniqueUrls.includes(u)) uniqueUrls.push(u);
      }
    }

    console.log("[Axiom] Extracted:", {
      tweetText: tweetText.substring(0, 100) + (tweetText.length > 100 ? "..." : ""),
      authorHandle,
      tweetUrl,
      urlCount: uniqueUrls.length,
      imageCount: mediaUrls.length,
      hasQuote: !!quotedTweet,
      hasCard: !!articleCard,
    });

    return {
      tweetText,
      authorHandle,
      authorName,
      tweetUrl,
      embeddedUrls: uniqueUrls,
      mediaUrls,
      quotedTweet,
      articleCard,
    };
  }

  // --- Extract a single tweet's basic info from an article element ---
  function extractSingleTweet(article) {
    const { text } = extractText(article);
    const { authorHandle, authorName } = extractAuthor(article);
    let tweetUrl = "";
    const timeEl = article.querySelector("time");
    if (timeEl) {
      const timeLink = timeEl.closest("a");
      if (timeLink) tweetUrl = timeLink.href;
    }
    return { text, authorHandle, authorName, tweetUrl };
  }

  // --- Detect and extract a thread from the detail page ---
  function extractThread(articles) {
    // On a tweet detail page, the thread structure is:
    // - Thread tweets (same author) appear ABOVE the focused tweet
    // - The focused tweet is the one matching the URL
    // - Replies from others appear BELOW
    //
    // We capture all tweets up to and including the focused tweet.
    // The focused tweet becomes the "main" tweet; preceding ones are thread context.

    const currentPath = window.location.pathname;
    const threadParts = [];
    let focusedIndex = -1;

    for (let i = 0; i < articles.length; i++) {
      const info = extractSingleTweet(articles[i]);
      threadParts.push({ ...info, article: articles[i], index: i });

      // Check if this is the focused tweet (URL matches current page)
      if (info.tweetUrl && currentPath.includes(info.tweetUrl.replace(/^https?:\/\/[^/]+/, ""))) {
        focusedIndex = i;
      }
    }

    // If we couldn't identify the focused tweet by URL, use heuristics:
    // The focused tweet is usually the last tweet before replies start
    // (replies are from different authors)
    if (focusedIndex === -1 && threadParts.length > 0) {
      // Find the URL author
      const urlMatch = currentPath.match(/^\/([A-Za-z0-9_]{1,15})\/status/);
      const urlAuthor = urlMatch ? urlMatch[1].toLowerCase() : "";

      if (urlAuthor) {
        // Find the last tweet from this author (before different authors appear)
        for (let i = 0; i < threadParts.length; i++) {
          if (threadParts[i].authorHandle.toLowerCase() === urlAuthor) {
            focusedIndex = i;
          } else if (focusedIndex >= 0) {
            break; // Different author after our author = replies started
          }
        }
      }

      // Still nothing? Default to first tweet
      if (focusedIndex === -1) focusedIndex = 0;
    }

    return { threadParts, focusedIndex };
  }

  // --- Extract from full page (for detail views / articles / threads) ---
  function extractFromPage() {
    console.log("[Axiom] Extracting from page:", window.location.href);

    const articles = document.querySelectorAll('article[data-testid="tweet"]');

    // --- Thread detection ---
    if (articles.length > 0) {
      const { threadParts, focusedIndex } = extractThread([...articles]);

      if (focusedIndex >= 0) {
        const focused = threadParts[focusedIndex];
        const focusedData = extractTweetData(focused.article);

        // Collect ALL conversation context ABOVE the focused tweet
        // This includes the original tweet, any replies leading up to it,
        // and the user's own thread tweets -- the full conversation.
        const threadContext = [];
        for (let i = 0; i < focusedIndex; i++) {
          const part = threadParts[i];
          if (part.text) {
            const partUrls = [...extractUrls(part.article)];
            const partQuote = extractQuotedTweet(part.article);
            const partCard = extractArticleCard(part.article);

            threadContext.push({
              type: "conversation",
              position: i + 1,
              author: part.authorHandle,
              text: part.text,
              urls: partUrls,
              quoted_tweet: partQuote,
              article_card: partCard,
            });

            for (const u of partUrls) {
              if (!focusedData.embeddedUrls.includes(u)) {
                focusedData.embeddedUrls.push(u);
              }
            }
            if (partCard?.url && !focusedData.embeddedUrls.includes(partCard.url)) {
              focusedData.embeddedUrls.push(partCard.url);
            }
          }
        }

        // Prepend thread context to the existing context_thread
        if (threadContext.length > 0) {
          focusedData.threadContext = threadContext;
        }

        // Use current page URL if we didn't get one
        if (!focusedData.tweetUrl) {
          focusedData.tweetUrl = window.location.href;
        }

        console.log("[Axiom] Extracted thread:", {
          focused: focusedData.tweetText.substring(0, 80) + "...",
          threadTweets: threadContext.length,
          totalUrls: focusedData.embeddedUrls.length,
        });

        return focusedData;
      }
    }

    // --- Fallback: primary column ---
    const mainContent =
      document.querySelector('[data-testid="primaryColumn"]') ||
      document.querySelector('main[role="main"]') ||
      document.querySelector("main");

    if (mainContent) {
      const data = extractTweetData(mainContent);
      if (data.tweetText || data.articleCard || data.quotedTweet) {
        console.log("[Axiom] Extracted from primary column");
        return data;
      }
    }

    // --- Nuclear fallback: grab all visible text ---
    console.log("[Axiom] Falling back to full-page text extraction");
    const column =
      document.querySelector('[data-testid="primaryColumn"]') ||
      document.querySelector("main") ||
      document.body;

    const textBlocks = [];
    const walker = document.createTreeWalker(column, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t.length > 15) {
        const parent = node.parentElement;
        if (parent && !parent.closest("nav") && !parent.closest("header") &&
            !parent.closest('[role="group"]') && !parent.closest("button")) {
          textBlocks.push(t);
        }
      }
    }

    const fullText = textBlocks.join("\n").substring(0, 3000);
    const allUrls = [...extractUrls(column)];
    const urlMatch = window.location.pathname.match(/^\/([A-Za-z0-9_]{1,15})\/status/);
    const authorHandle = urlMatch ? urlMatch[1] : "";

    if (fullText.length > 20 || allUrls.length > 0) {
      console.log("[Axiom] Full-page fallback:", fullText.length, "chars,", allUrls.length, "urls");
      return {
        tweetText: fullText,
        authorHandle,
        authorName: "",
        tweetUrl: window.location.href,
        embeddedUrls: allUrls,
        quotedTweet: null,
        articleCard: null,
      };
    }

    console.log("[Axiom] Could not extract anything from page");
    return null;
  }

  // --- Send tweet to Supabase ---
  async function sendTweet(tweetData, button, responseMode = "short") {
    const config = await new Promise((resolve) => {
      chrome.storage.sync.get(
        ["supabaseUrl", "supabaseAnonKey"],
        (result) => resolve(result)
      );
    });

    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      showToast("Configure Supabase in extension settings first.", "error");
      return;
    }

    if (button) {
      button.classList.add("axiom-sending");
      const label = button.querySelector(".axiom-label");
      if (label) label.textContent = "...";
    }

    try {
      const contextThread = [];

      // Thread tweets (preceding/following tweets by same author)
      if (tweetData.threadContext) {
        for (const t of tweetData.threadContext) {
          contextThread.push(t);
        }
      }

      if (tweetData.quotedTweet) {
        contextThread.push({
          type: "quoted_tweet",
          author: tweetData.quotedTweet.author,
          text: tweetData.quotedTweet.text,
          urls: tweetData.quotedTweet.urls,
        });
      }

      if (tweetData.articleCard) {
        contextThread.push({
          type: "article_card",
          title: tweetData.articleCard.title,
          description: tweetData.articleCard.description,
          url: tweetData.articleCard.url,
          domain: tweetData.articleCard.domain,
        });
      }

      const response = await fetch(
        `${config.supabaseUrl}/functions/v1/ingest-tweet`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${config.supabaseAnonKey}`,
          },
          body: JSON.stringify({
            tweet_url: tweetData.tweetUrl,
            author_handle: tweetData.authorHandle,
            author_name: tweetData.authorName,
            tweet_text: tweetData.tweetText,
            embedded_urls: tweetData.embeddedUrls,
            media_urls: tweetData.mediaUrls || [],
            context_thread: contextThread,
            response_mode: responseMode,
          }),
        }
      );

      const result = await response.json();

      if (response.ok && result.ok) {
        if (button) {
          button.classList.remove("axiom-sending");
          button.classList.add("axiom-success");
          const label = button.querySelector(".axiom-label");
          if (label) label.textContent = "Evaluating...";
        }
        const urlCount = tweetData.embeddedUrls.length;
        const imgCount = (tweetData.mediaUrls || []).length;
        const modeLabel = responseMode === "long" ? "long-form" : "short";
        const extras = [];
        if (urlCount > 0) extras.push(`${urlCount} link(s)`);
        if (imgCount > 0) extras.push(`${imgCount} image(s)`);
        showToast(
          extras.length > 0
            ? `Tweet + ${extras.join(" + ")} captured (${modeLabel}) — evaluating...`
            : `Tweet captured (${modeLabel}) — evaluating...`,
          "success"
        );

        // Poll for the draft response
        if (result.tweet_id) {
          pollForDraft(result.tweet_id, button);
        }
      } else {
        throw new Error(result.error || "Unknown error");
      }
    } catch (err) {
      if (button) {
        button.classList.remove("axiom-sending");
        button.classList.add("axiom-error");
        const label = button.querySelector(".axiom-label");
        if (label) label.textContent = "Error";
        setTimeout(() => {
          button.classList.remove("axiom-error");
          const label2 = button.querySelector(".axiom-label");
          if (label2) label2.textContent = "Axiom";
        }, 3000);
      }
      showToast(`Failed: ${err.message}`, "error");
    }
  }

  // --- Poll for draft response after evaluation ---
  async function pollForDraft(tweetId, button) {
    const config = await new Promise((resolve) => {
      chrome.storage.sync.get(["supabaseUrl", "supabaseAnonKey"], (r) => resolve(r));
    });

    if (!config.supabaseUrl || !config.supabaseAnonKey) return;

    const headers = {
      apikey: config.supabaseAnonKey,
      Authorization: `Bearer ${config.supabaseAnonKey}`,
    };

    let attempts = 0;
    const maxAttempts = 20; // ~2 minutes max
    const interval = 6000; // 6 seconds

    const poll = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(poll);
        if (button) {
          const label = button.querySelector(".axiom-label");
          if (label) label.textContent = "Timeout";
        }
        return;
      }

      try {
        // Check if tweet is processed
        const tweetRes = await fetch(
          `${config.supabaseUrl}/rest/v1/ingested_tweets?id=eq.${tweetId}&select=processed`,
          { headers }
        );
        const tweets = await tweetRes.json();
        if (!tweets?.[0]?.processed) return; // Not ready yet

        // Fetch draft
        const draftRes = await fetch(
          `${config.supabaseUrl}/rest/v1/draft_responses?tweet_id=eq.${tweetId}&status=eq.pending&select=draft_text,tone&limit=1`,
          { headers }
        );
        const drafts = await draftRes.json();

        clearInterval(poll);

        if (drafts && drafts.length > 0) {
          const draftText = drafts[0].draft_text;
          const tone = drafts[0].tone;

          if (button) {
            button.classList.remove("axiom-success");
            button.classList.add("axiom-ready");
            button.title = `Click to copy: "${draftText}"`;
            const label = button.querySelector(".axiom-label");
            if (label) label.textContent = "Copy Reply";

            // Replace click handler to copy draft
            const newBtn = button.cloneNode(true);
            button.parentNode.replaceChild(newBtn, button);
            newBtn.addEventListener("click", async (e) => {
              e.preventDefault();
              e.stopPropagation();
              await navigator.clipboard.writeText(draftText);
              showToast(`Copied (${tone}): "${draftText}"`, "success");
              const lbl = newBtn.querySelector(".axiom-label");
              if (lbl) lbl.textContent = "Copied!";
              setTimeout(() => { if (lbl) lbl.textContent = "Copy Reply"; }, 2000);
            });
          }

          showToast(`Draft ready (${tone}) — click "Copy Reply" on the tweet.`, "info");
        } else {
          // Evaluated but no draft (skipped)
          if (button) {
            button.classList.remove("axiom-success");
            const label = button.querySelector(".axiom-label");
            if (label) label.textContent = "Skipped";
          }
        }
      } catch (err) {
        console.error("[Axiom] Poll error:", err);
      }
    }, interval);
  }

  // --- Inject button into a tweet article (timeline view) ---
  function injectButton(article) {
    if (article.hasAttribute(AXIOM_MARKER)) return;
    article.setAttribute(AXIOM_MARKER, "true");

    // Try multiple selectors for the action bar
    const actionBar =
      article.querySelector('[role="group"]') ||
      article.querySelector('[data-testid="reply"]')?.closest('div[role="group"]');
    if (!actionBar) return;

    const btn = document.createElement("button");
    btn.className = "axiom-btn";
    btn.innerHTML = `${AXIOM_ICON}<span class="axiom-label">Axiom</span>`;
    btn.title = "Evaluate with Axiom (Shift-click for long-form reply)";

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();

      const data = extractTweetData(article);
      if (!data.tweetText && !data.articleCard && !data.quotedTweet) {
        showToast("Could not extract any content from this tweet.", "error");
        return;
      }

      // Shift-click = long-form response
      const mode = e.shiftKey ? "long" : "short";
      if (mode === "long") {
        btn.classList.add("axiom-long");
      }
      sendTweet(data, btn, mode);
    });

    actionBar.appendChild(btn);
  }

  // --- Floating Action Button (FAB) for detail/article pages ---
  function createFAB() {
    if (document.getElementById("axiom-fab")) return;

    const fab = document.createElement("button");
    fab.id = "axiom-fab";
    fab.className = "axiom-fab";
    fab.innerHTML = `${AXIOM_ICON}<span class="axiom-fab-label">Axiom</span>`;
    fab.title = "Capture with Axiom (Shift-click for long-form reply)";

    fab.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();

      const data = extractFromPage();
      if (!data) {
        showToast("Could not extract content from this page.", "error");
        return;
      }

      if (!data.tweetText && !data.articleCard && !data.quotedTweet) {
        showToast("No tweet or article content found on this page.", "error");
        return;
      }

      // Shift-click = long-form response
      const mode = e.shiftKey ? "long" : "short";

      fab.classList.add("axiom-sending");
      const fabLabel = fab.querySelector(".axiom-fab-label");
      fabLabel.textContent = mode === "long" ? "Long..." : "...";

      sendTweet(data, null, mode).then(() => {
        fab.classList.remove("axiom-sending");
        fab.classList.add("axiom-success");
        fabLabel.textContent = "Sent";
        setTimeout(() => {
          fab.classList.remove("axiom-success");
          fabLabel.textContent = "Axiom";
        }, 3000);
      });
    });

    document.body.appendChild(fab);
  }

  // --- Scan and inject into all visible tweets ---
  function scanAndInject() {
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    articles.forEach(injectButton);

    // Also inject the FAB on detail / article pages
    createFAB();
  }

  // --- MutationObserver for dynamically loaded tweets ---
  const observer = new MutationObserver((mutations) => {
    let shouldScan = false;
    for (const mutation of mutations) {
      if (mutation.addedNodes.length > 0) {
        shouldScan = true;
        break;
      }
    }
    if (shouldScan) {
      clearTimeout(observer._scanTimeout);
      observer._scanTimeout = setTimeout(scanAndInject, 200);
    }
  });

  // Re-scan on URL changes (X uses client-side routing)
  let lastUrl = location.href;
  const urlObserver = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      // Small delay for new page content to render
      setTimeout(scanAndInject, 500);
    }
  });

  // --- Init ---
  function init() {
    scanAndInject();
    observer.observe(document.body, { childList: true, subtree: true });
    urlObserver.observe(document.body, { childList: true, subtree: true });
    console.log("[Axiom] Content script loaded — watching for tweets + articles.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
