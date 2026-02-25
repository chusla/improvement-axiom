// Supabase Edge Function: evaluate-tweet
// Evaluates an ingested tweet through the Axiom framework using Claude,
// then generates a draft response. Fetches linked articles for context.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import Anthropic from "https://esm.sh/@anthropic-ai/sdk@0.39.0";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.43/deno-dom-wasm.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// --- Image fetching ---

const MAX_IMAGES = 4; // max images to send to Claude per tweet
const IMAGE_FETCH_TIMEOUT_MS = 10000;

async function fetchImageAsBase64(url: string): Promise<{
  url: string;
  media_type: string;
  base64: string;
} | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), IMAGE_FETCH_TIMEOUT_MS);

    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (compatible; AxiomBot/0.1; +https://github.com/improvement-axiom)",
      },
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!response.ok) return null;

    const contentType = response.headers.get("content-type") || "";

    // Map content-type to Claude's accepted media types
    let mediaType = "image/jpeg";
    if (contentType.includes("png")) mediaType = "image/png";
    else if (contentType.includes("gif")) mediaType = "image/gif";
    else if (contentType.includes("webp")) mediaType = "image/webp";

    const arrayBuffer = await response.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);

    // Deno-compatible base64 encoding
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);

    // Skip if image is too large (>5MB base64 ≈ 6.6MB encoded)
    if (base64.length > 6_600_000) {
      console.warn(`Image too large (${base64.length} chars), skipping: ${url}`);
      return null;
    }

    return { url, media_type: mediaType, base64 };
  } catch (err) {
    console.error(`Failed to fetch image: ${url}`, err.message);
    return null;
  }
}

async function fetchAllImages(
  urls: string[]
): Promise<Array<{ url: string; media_type: string; base64: string }>> {
  if (!urls || urls.length === 0) return [];

  // Deduplicate and limit
  const unique = [...new Set(urls)].slice(0, MAX_IMAGES);
  const results = await Promise.allSettled(unique.map(fetchImageAsBase64));
  return results
    .filter((r) => r.status === "fulfilled" && r.value !== null)
    .map((r) => (r as PromiseFulfilledResult<NonNullable<Awaited<ReturnType<typeof fetchImageAsBase64>>>>).value);
}

// --- Article fetching & extraction ---

const MAX_ARTICLE_LENGTH = 4000; // chars to send to Claude
const FETCH_TIMEOUT_MS = 8000;

async function fetchArticleContent(url: string): Promise<{
  url: string;
  title: string;
  text: string;
  resolved_url: string;
  error?: string;
}> {
  const result = { url, title: "", text: "", resolved_url: url, error: undefined as string | undefined };

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (compatible; AxiomBot/0.1; +https://github.com/improvement-axiom)",
        Accept: "text/html,application/xhtml+xml,*/*",
      },
      redirect: "follow",
      signal: controller.signal,
    });

    clearTimeout(timeout);
    result.resolved_url = response.url;

    if (!response.ok) {
      result.error = `HTTP ${response.status}`;
      return result;
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("text/html") && !contentType.includes("text/plain")) {
      result.error = `Non-text content: ${contentType}`;
      return result;
    }

    const html = await response.text();

    // Parse HTML and extract readable text
    const doc = new DOMParser().parseFromString(html, "text/html");
    if (!doc) {
      result.error = "Failed to parse HTML";
      return result;
    }

    // Extract title
    const titleEl = doc.querySelector("title");
    const ogTitle = doc.querySelector('meta[property="og:title"]');
    result.title =
      ogTitle?.getAttribute("content") ||
      titleEl?.textContent?.trim() ||
      "";

    // Extract OG description as fallback
    const ogDesc = doc.querySelector('meta[property="og:description"]')?.getAttribute("content") || "";

    // Remove script, style, nav, footer, header elements
    const removeTags = ["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"];
    for (const tag of removeTags) {
      const elements = doc.querySelectorAll(tag);
      for (const el of elements) {
        el.remove();
      }
    }

    // Try <article> first, then <main>, then fall back to <body>
    const contentEl =
      doc.querySelector("article") ||
      doc.querySelector('[role="main"]') ||
      doc.querySelector("main") ||
      doc.querySelector(".post-content") ||
      doc.querySelector(".article-content") ||
      doc.querySelector(".entry-content") ||
      doc.body;

    let text = contentEl?.textContent || "";

    // Clean up whitespace
    text = text
      .replace(/\s+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    // If article extraction got very little, use OG description
    if (text.length < 100 && ogDesc) {
      text = ogDesc;
    }

    // Truncate to max length
    if (text.length > MAX_ARTICLE_LENGTH) {
      text = text.substring(0, MAX_ARTICLE_LENGTH) + "... [truncated]";
    }

    result.text = text;
  } catch (err) {
    result.error = err.name === "AbortError" ? "Timeout" : err.message;
  }

  return result;
}

async function fetchAllArticles(
  urls: string[],
  contextThread: Array<Record<string, unknown>>
): Promise<{
  articles: Array<{ url: string; title: string; text: string; resolved_url: string }>;
  quotedTweets: Array<Record<string, unknown>>;
  threadTweets: Array<Record<string, unknown>>;
}> {
  const articles: Array<{ url: string; title: string; text: string; resolved_url: string }> = [];
  const quotedTweets: Array<Record<string, unknown>> = [];
  const threadTweets: Array<Record<string, unknown>> = [];

  // Separate thread/conversation tweets, quoted tweets, and article cards
  for (const item of contextThread || []) {
    if (item.type === "thread_tweet" || item.type === "conversation") {
      threadTweets.push(item);
      // Also fetch URLs from thread tweets
      if (Array.isArray(item.urls)) {
        urls = [...urls, ...item.urls as string[]];
      }
      if (item.article_card && (item.article_card as Record<string, unknown>).url) {
        urls.push((item.article_card as Record<string, unknown>).url as string);
      }
    } else if (item.type === "quoted_tweet") {
      quotedTweets.push(item);
      if (Array.isArray(item.urls)) {
        urls = [...urls, ...item.urls as string[]];
      }
    } else if (item.type === "article_card" && item.url) {
      if (!urls.includes(item.url as string)) {
        urls.push(item.url as string);
      }
    }
  }

  // Deduplicate URLs and skip x.com/twitter.com (auth-walled, extension handles these)
  const uniqueUrls = [...new Set(urls)].filter(
    (u) =>
      u &&
      u.startsWith("http") &&
      !u.match(/^https?:\/\/(x\.com|twitter\.com)\//)
  );

  // Fetch up to 3 articles in parallel
  const toFetch = uniqueUrls.slice(0, 3);
  if (toFetch.length > 0) {
    const results = await Promise.allSettled(toFetch.map(fetchArticleContent));
    for (const r of results) {
      if (r.status === "fulfilled" && r.value.text) {
        articles.push(r.value);
      }
    }
  }

  return { articles, quotedTweets, threadTweets };
}

// --- Prompt construction ---

function buildEvalContext(
  tweet: Record<string, unknown>,
  articles: Array<{ url: string; title: string; text: string; resolved_url: string }>,
  quotedTweets: Array<Record<string, unknown>>,
  threadTweets: Array<Record<string, unknown>>
): string {
  let context = "";

  // Add conversation context first (preceding tweets set the scene)
  if (threadTweets.length > 0) {
    context += "--- Conversation preceding this tweet ---";
    for (const tt of threadTweets) {
      context += `\n[${tt.position || ""}] @${tt.author || "unknown"}: "${tt.text}"`;
    }
    context += `\n\n--- Tweet to evaluate (this is what we are replying to) ---\n`;
  }

  context += `"${tweet.tweet_text}"\n\nby @${tweet.author_handle || "unknown"}`;

  if (quotedTweets.length > 0) {
    context += "\n\n--- Quoted tweet(s) ---";
    for (const qt of quotedTweets) {
      context += `\n@${qt.author || "unknown"}: "${qt.text}"`;
    }
  }

  if (articles.length > 0) {
    context += "\n\n--- Linked article(s) ---";
    for (const art of articles) {
      context += `\n\n[${art.title || art.resolved_url}]`;
      if (art.text) {
        context += `\n${art.text}`;
      }
    }
  }

  return context;
}

function buildDraftContext(
  tweet: Record<string, unknown>,
  evaluation: Record<string, unknown>,
  articles: Array<{ url: string; title: string; text: string }>,
  quotedTweets: Array<Record<string, unknown>>,
  threadTweets: Array<Record<string, unknown>>
): string {
  let context = "";

  if (threadTweets.length > 0) {
    context += "Preceding conversation:\n";
    for (const tt of threadTweets) {
      const snippet = (tt.text as string).length > 400
        ? (tt.text as string).substring(0, 400) + "..."
        : tt.text;
      context += `@${tt.author || "unknown"}: "${snippet}"\n`;
    }
    context += "\nYou are replying to this tweet ";
  } else {
    context += "You are replying to this tweet ";
  }

  context += `by @${tweet.author_handle || "unknown"}:\n"${tweet.tweet_text}"`;

  if (quotedTweets.length > 0) {
    for (const qt of quotedTweets) {
      context += `\n\nQuoted @${qt.author || "unknown"}: "${qt.text}"`;
    }
  }

  if (articles.length > 0) {
    context += "\n\nLinked article summary:";
    for (const art of articles) {
      const snippet = art.text.length > 500 ? art.text.substring(0, 500) + "..." : art.text;
      context += `\n- ${art.title || "Article"}: ${snippet}`;
    }
  }

  context += `\n\nAxiom evaluation: ${JSON.stringify(evaluation)}`;
  context += "\n\nDraft a reply.";

  return context;
}

// --- System prompts ---
// Prompts are stored in Supabase system_prompts table.
// Source of truth: prompts/*.md — sync with: deno run --allow-env --allow-net --allow-read scripts/prompts-push.ts

const _promptCache: Record<string, string> = {};

async function getPrompt(
  supabase: ReturnType<typeof createClient>,
  slug: string
): Promise<string> {
  if (_promptCache[slug]) return _promptCache[slug];
  const { data, error } = await supabase
    .from("system_prompts")
    .select("prompt_text")
    .eq("slug", slug)
    .eq("is_active", true)
    .single();
  if (error || !data) throw new Error(`Prompt not found in DB: ${slug}`);
  _promptCache[slug] = data.prompt_text as string;
  return _promptCache[slug];
}

// --- JSON parsing helper ---

function parseJsonResponse(raw: string, fallback: Record<string, unknown>): Record<string, unknown> {
  let text = raw.trim();
  // Strip markdown code fences if Claude wrapped the JSON
  text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();

  // Attempt 1: direct parse
  try {
    return JSON.parse(text);
  } catch {
    // Attempt 2: fix literal newlines inside JSON string values
    try {
      const fixed = text.replace(
        /("(?:draft|reason)":\s*")([\s\S]*?)("(?:\s*[,}]))/g,
        (_match, prefix, content, suffix) => {
          const escaped = content
            .replace(/\\/g, "\\\\")
            .replace(/\n/g, "\\n")
            .replace(/\r/g, "\\r")
            .replace(/\t/g, "\\t");
          return prefix + escaped + suffix;
        }
      );
      return JSON.parse(fixed);
    } catch { /* fall through */ }

    // Attempt 3: regex extraction
    try {
      const draftMatch = text.match(/"draft"\s*:\s*"([\s\S]*?)"\s*,\s*"tone"/);
      const toneMatch = text.match(/"tone"\s*:\s*"(\w+)"/);
      if (draftMatch) {
        return {
          draft: draftMatch[1].replace(/\\n/g, "\n").replace(/\\"/g, '"'),
          tone: toneMatch ? toneMatch[1] : "thoughtful",
        };
      }
    } catch { /* fall through */ }

    // Attempt 4: Claude returned raw prose instead of JSON.
    // If it doesn't start with '{', treat the entire text as the draft.
    if (!text.startsWith("{")) {
      console.log("Response is raw prose, not JSON. Treating as draft text.");
      return { draft: text, tone: "thoughtful" };
    }

    console.error("JSON parse failed after all attempts. Raw:", text.substring(0, 500));
    return fallback;
  }
}

// --- Main handler ---

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anthropicKey = Deno.env.get("ANTHROPIC_API_KEY")!;

    const supabase = createClient(supabaseUrl, supabaseKey);
    const anthropic = new Anthropic({ apiKey: anthropicKey });

    // Fetch all system prompts upfront (cached after first call per instance)
    const [evaluationPrompt, shortPrompt, longPrompt] = await Promise.all([
      getPrompt(supabase, "arete.evaluation"),
      getPrompt(supabase, "arete.short"),
      getPrompt(supabase, "arete.long"),
    ]);

    const { tweet_id } = await req.json();

    if (!tweet_id) {
      return new Response(
        JSON.stringify({ error: "tweet_id is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Fetch the tweet
    const { data: tweet, error: fetchError } = await supabase
      .from("ingested_tweets")
      .select("*")
      .eq("id", tweet_id)
      .single();

    if (fetchError || !tweet) {
      throw new Error(`Tweet not found: ${tweet_id}`);
    }

    // Fetch model config
    const { data: modelConfig } = await supabase
      .from("agent_config")
      .select("value")
      .eq("key", "model")
      .single();

    const model = modelConfig?.value || "claude-sonnet-4-5";

    // --- Step 0: Fetch linked articles and extract content ---
    const allUrls = [
      ...(tweet.embedded_urls || []),
    ];

    // Also extract URLs from context_thread article cards
    for (const item of (tweet.context_thread || [])) {
      if (item.type === "article_card" && item.url) {
        allUrls.push(item.url);
      }
    }

    // Fetch articles and images in parallel
    const [articleResult, images] = await Promise.all([
      fetchAllArticles(allUrls, tweet.context_thread || []),
      fetchAllImages(tweet.media_urls || []),
    ]);

    const { articles, quotedTweets, threadTweets } = articleResult;

    // --- Store images in Supabase Storage ---
    const storedImageUrls: string[] = [];
    for (let i = 0; i < images.length; i++) {
      const img = images[i];
      const ext = img.media_type.split("/")[1] || "jpg";
      const path = `tweets/${tweet_id}/${i}.${ext}`;

      // Decode base64 back to binary for storage upload
      const binaryStr = atob(img.base64);
      const bytes = new Uint8Array(binaryStr.length);
      for (let j = 0; j < binaryStr.length; j++) {
        bytes[j] = binaryStr.charCodeAt(j);
      }

      const { error: uploadError } = await supabase.storage
        .from("tweet-images")
        .upload(path, bytes.buffer, {
          contentType: img.media_type,
          upsert: true,
        });

      if (uploadError) {
        console.error(`Image upload failed [${path}]:`, uploadError.message);
      } else {
        const { data: urlData } = supabase.storage
          .from("tweet-images")
          .getPublicUrl(path);
        if (urlData?.publicUrl) {
          storedImageUrls.push(urlData.publicUrl);
        }
      }
    }

    // Store fetched content and image storage URLs back to the tweet
    if (articles.length > 0 || images.length > 0) {
      await supabase
        .from("ingested_tweets")
        .update({
          fetched_content: {
            articles: articles.map((a) => ({
              url: a.url,
              resolved_url: a.resolved_url,
              title: a.title,
              text: a.text,
              text_length: a.text.length,
            })),
            images_fetched: images.length,
            stored_image_urls: storedImageUrls,
            fetched_at: new Date().toISOString(),
          },
        })
        .eq("id", tweet_id);
    }

    // --- Step 1: Evaluate the tweet (with article + image context) ---
    const evalContext = buildEvalContext(tweet, articles, quotedTweets, threadTweets);

    // Build multimodal content: text context + images
    const evalContent: Array<Record<string, unknown>> = [];

    // Add images first so Claude sees them before the text prompt
    for (const img of images) {
      evalContent.push({
        type: "image",
        source: {
          type: "base64",
          media_type: img.media_type,
          data: img.base64,
        },
      });
    }

    // Add text context
    evalContent.push({ type: "text", text: evalContext });

    // Add image instruction if images are present
    if (images.length > 0) {
      evalContent.push({
        type: "text",
        text: `\n\nThis tweet includes ${images.length} image(s) shown above. Evaluate the FULL content — both the text and what's in the images. If the image contains text, charts, diagrams, screenshots, or memes, incorporate that content into your evaluation.`,
      });
    }

    const evalResponse = await anthropic.messages.create({
      model,
      max_tokens: 512,
      system: evaluationPrompt,
      messages: [{ role: "user", content: evalContent }],
    });

    const evalText =
      evalResponse.content[0].type === "text"
        ? evalResponse.content[0].text
        : "";

    const evaluation = parseJsonResponse(evalText, {
      quality_score: 0.5,
      intention: "ambiguous",
      quadrant: "Ambiguous",
      resonance_potential: 0.5,
      reasoning: "Failed to parse evaluation — defaulting to neutral.",
    });

    // Store evaluation
    const { data: evalRecord, error: evalInsertError } = await supabase
      .from("axiom_evaluations")
      .insert({
        tweet_id,
        quality_score: evaluation.quality_score,
        intention: evaluation.intention,
        quadrant: evaluation.quadrant,
        resonance_potential: evaluation.resonance_potential,
        evaluation_reasoning: evaluation.reasoning,
        raw_llm_response: evaluation,
        model_used: model,
      })
      .select()
      .single();

    if (evalInsertError) {
      console.error("Eval insert error:", evalInsertError);
    }

    // --- Step 2: Generate draft response (with article + image context) ---
    const responseMode = tweet.response_mode || "short";
    const isLong = responseMode === "long";
    const draftContext = buildDraftContext(tweet, evaluation, articles, quotedTweets, threadTweets);

    // Build multimodal content for draft (include images so reply can reference them)
    const draftContent: Array<Record<string, unknown>> = [];
    for (const img of images) {
      draftContent.push({
        type: "image",
        source: {
          type: "base64",
          media_type: img.media_type,
          data: img.base64,
        },
      });
    }
    draftContent.push({ type: "text", text: draftContext });
    if (images.length > 0) {
      draftContent.push({
        type: "text",
        text: `\nThe tweet includes ${images.length} image(s) shown above. Reference specific content from the images in your reply where relevant.`,
      });
    }

    const draftResponse = await anthropic.messages.create({
      model,
      max_tokens: isLong ? 8192 : 350,
      system: isLong ? longPrompt : shortPrompt,
      messages: [{ role: "user", content: draftContent }],
    });

    const draftText =
      draftResponse.content[0].type === "text"
        ? draftResponse.content[0].text
        : "";

    const draft = parseJsonResponse(draftText, {
      skip: true,
      reason: "Failed to parse draft response.",
    });

    // Post-process draft: enforce style rules the model may ignore
    if (!draft.skip && draft.draft) {
      let cleanDraft = (draft.draft as string)
        .replace(/\u2014/g, ", ")   // em dash → comma
        .replace(/\u2013/g, ", ");  // en dash → comma

      if (isLong) {
        // Preserve paragraph breaks but clean up excess whitespace
        cleanDraft = cleanDraft
          .split(/\n\s*\n/)                    // split on paragraph breaks
          .map((p) => p.replace(/\s+/g, " ").trim())  // clean each paragraph
          .filter((p) => p.length > 0)         // drop empties
          .join("\n\n");                        // rejoin with clean double newline
      } else {
        cleanDraft = cleanDraft
          .replace(/\s{2,}/g, " ")             // collapse all whitespace for short
          .trim();
      }

      // Enforce length limits per mode
      const maxLen = isLong ? 4000 : 280;
      if (cleanDraft.length > maxLen) {
        cleanDraft = cleanDraft.substring(0, maxLen - 3) + "...";
      }

      draft.draft = cleanDraft;
    }

    // Store draft (unless skipped)
    if (!draft.skip) {
      const { error: draftInsertError } = await supabase
        .from("draft_responses")
        .insert({
          tweet_id,
          evaluation_id: evalRecord?.id || null,
          draft_text: draft.draft as string,
          tone: draft.tone as string,
          response_mode: responseMode,
          axiom_aligned: true,
          status: "pending",
        });

      if (draftInsertError) {
        console.error("Draft insert error:", draftInsertError);
      }
    }

    // Mark tweet as processed
    await supabase
      .from("ingested_tweets")
      .update({ processed: true })
      .eq("id", tweet_id);

    return new Response(
      JSON.stringify({
        ok: true,
        evaluation,
        draft: draft.skip ? null : draft,
        skipped: !!draft.skip,
        skip_reason: draft.reason || null,
        response_mode: responseMode,
        articles_fetched: articles.length,
        images_analyzed: images.length,
        images_stored: storedImageUrls.length,
        quoted_tweets: quotedTweets.length,
        thread_tweets: threadTweets.length,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("Evaluate error:", err);
    return new Response(
      JSON.stringify({ error: err.message || "Internal error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
