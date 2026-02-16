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

  // Separate thread tweets, quoted tweets, and article cards
  for (const item of contextThread || []) {
    if (item.type === "thread_tweet") {
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

  // Add thread context first (earlier tweets set the scene)
  if (threadTweets.length > 0) {
    context += "--- Thread context (earlier tweets by same author) ---";
    for (const tt of threadTweets) {
      context += `\n[${tt.position || ""}] @${tt.author || "unknown"}: "${tt.text}"`;
    }
    context += `\n\n--- Focused tweet (evaluate this one) ---\n`;
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
    context += "Thread context:\n";
    for (const tt of threadTweets) {
      const snippet = (tt.text as string).length > 200
        ? (tt.text as string).substring(0, 200) + "..."
        : tt.text;
      context += `[${tt.position || ""}] @${tt.author || "unknown"}: "${snippet}"\n`;
    }
    context += "\nFocused tweet ";
  } else {
    context += "Original tweet ";
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

const EVALUATION_SYSTEM_PROMPT = `You are the Improvement Axiom evaluator — an AI alignment framework that maps human activities onto two independent axes:

1. **Quality** (0.0–1.0): Signal depth, originality, evidence of craft, durability, growth-enabling properties.
2. **Intention** ("creative" or "consumptive"): Is the author building/contributing, or extracting/consuming?

These axes form four quadrants:
- HQ-Creative: High quality + creative intent (the target zone)
- HQ-Consumptive: High quality + consumptive intent (sophisticated extraction)
- LQ-Creative: Low quality + creative intent (earnest but rough)
- LQ-Consumptive: Low quality + consumptive intent (noise)

IMPORTANT: Intent is inferred from evidence, not assumed. A single tweet is low-evidence — keep confidence proportional.

When articles or linked content are provided, evaluate the FULL context — the tweet AND the article it references. Consider:
- Is the author sharing to inform/create value, or to extract engagement?
- Does the linked content have substance (research, original reporting, analysis)?
- Is the quote/retweet adding commentary that builds on the source?

You also assess **resonance_potential** (0.0–1.0): how likely is this tweet+content to inspire creative engagement in others?

Respond ONLY with valid JSON (no markdown fencing) matching this schema:
{
  "quality_score": <float 0.0-1.0>,
  "intention": "<creative|consumptive|ambiguous>",
  "quadrant": "<HQ-Creative|HQ-Consumptive|LQ-Creative|LQ-Consumptive|Ambiguous>",
  "resonance_potential": <float 0.0-1.0>,
  "reasoning": "<1-3 sentence explanation>"
}`;

const RESPONSE_SYSTEM_PROMPT = `You are a Twitter account guided by the Improvement Axiom framework.

## Voice & Style Rules
- Push conversations toward High-Quality Creative territory
- Add signal, not noise. Every word must earn its place.
- Be genuine, warm, and never preachy or moralistic
- Ask a question or offer a reframe when appropriate
- Match the energy of the original tweet
- NEVER use framework jargon (quadrants, consumptive, resonance scores, etc.)
- When replying to article shares: engage with the SUBSTANCE of the article
- When replying to quote tweets/threads: acknowledge the broader context
- You are NOT a bot. You are a thoughtful human voice.

## HARD CHARACTER LIMIT
Your reply MUST be under 260 characters (not 280 -- leave a safety margin).
Count carefully. If your draft is too long, CUT IT DOWN. Prefer:
- Short punchy sentences over long compound ones
- One sharp question over two decent ones
- Fewer words, more weight

## BANNED
- NEVER use em dashes (—). Use commas, periods, or just start a new sentence.
- NEVER use en dashes (–) either
- No hashtags, no emojis unless the original tweet uses them

## When to reply
ALWAYS draft a reply. Even for low-quality tweets, a well-placed question can
shift the energy. The ONLY exception is pure spam/bot content. In that rare case:
{"skip": true, "reason": "<brief reason>"}

Otherwise respond with valid JSON (no markdown fencing):
{"draft": "<your reply UNDER 260 chars>", "tone": "<thoughtful|challenging|supportive|playful|curious>"}`;

// --- JSON parsing helper ---

function parseJsonResponse(raw: string, fallback: Record<string, unknown>): Record<string, unknown> {
  let text = raw.trim();
  // Strip markdown code fences if Claude wrapped the JSON
  text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
  try {
    return JSON.parse(text);
  } catch {
    console.error("JSON parse failed. Raw:", text);
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

    const { articles, quotedTweets, threadTweets } = await fetchAllArticles(
      allUrls,
      tweet.context_thread || []
    );

    // Store fetched content (including full text) back to the tweet
    if (articles.length > 0) {
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
            fetched_at: new Date().toISOString(),
          },
        })
        .eq("id", tweet_id);
    }

    // --- Step 1: Evaluate the tweet (with article context) ---
    const evalContext = buildEvalContext(tweet, articles, quotedTweets, threadTweets);

    const evalResponse = await anthropic.messages.create({
      model,
      max_tokens: 512,
      system: EVALUATION_SYSTEM_PROMPT,
      messages: [{ role: "user", content: evalContext }],
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

    // --- Step 2: Generate draft response (with article context) ---
    const draftContext = buildDraftContext(tweet, evaluation, articles, quotedTweets, threadTweets);

    const draftResponse = await anthropic.messages.create({
      model,
      max_tokens: 350,
      system: RESPONSE_SYSTEM_PROMPT,
      messages: [{ role: "user", content: draftContext }],
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
        .replace(/\u2013/g, ", ")   // en dash → comma
        .replace(/\s{2,}/g, " ")    // collapse double spaces
        .trim();

      // Truncate to 280 if still over
      if (cleanDraft.length > 280) {
        cleanDraft = cleanDraft.substring(0, 277) + "...";
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
        articles_fetched: articles.length,
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
