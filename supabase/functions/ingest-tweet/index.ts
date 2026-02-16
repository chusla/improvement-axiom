// Supabase Edge Function: ingest-tweet
// Receives tweet data from the Chrome extension and stores it,
// then triggers evaluation via the evaluate-tweet function.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const {
      tweet_url, author_handle, author_name, tweet_text,
      context_thread, media_urls, embedded_urls,
      response_mode,
    } = await req.json();

    if (!tweet_url) {
      return new Response(
        JSON.stringify({ error: "tweet_url is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Insert the tweet
    const { data: tweet, error: insertError } = await supabase
      .from("ingested_tweets")
      .insert({
        tweet_url,
        author_handle: author_handle || null,
        author_name: author_name || null,
        tweet_text: tweet_text || "",
        context_thread: context_thread || [],
        media_urls: media_urls || [],
        embedded_urls: embedded_urls || [],
        response_mode: response_mode === "long" ? "long" : "short",
      })
      .select()
      .single();

    if (insertError) {
      throw insertError;
    }

    // Trigger evaluation asynchronously by calling the evaluate-tweet function
    const evalUrl = `${supabaseUrl}/functions/v1/evaluate-tweet`;
    fetch(evalUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${supabaseKey}`,
      },
      body: JSON.stringify({ tweet_id: tweet.id }),
    }).catch((err) => console.error("Failed to trigger evaluation:", err));

    return new Response(
      JSON.stringify({
        ok: true,
        tweet_id: tweet.id,
        message: "Tweet ingested, evaluation triggered.",
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("Ingest error:", err);
    return new Response(
      JSON.stringify({ error: err.message || "Internal error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
