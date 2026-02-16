# Improvement Axiom — Twitter Agent

A Chrome extension + Supabase Edge Functions pipeline that lets you capture tweets from X/Twitter, evaluate them through the Axiom framework using Claude, and review AI-generated draft replies.

## Architecture

```
You on X.com                   Supabase                          Claude
─────────────                  ────────                          ──────
Browse Twitter normally        
  │                            
  ├─ Click "Axiom" on tweet    
  │         │                  
  │         └───────────────► ingest-tweet edge function
  │                              │
  │                              ├─ Store in ingested_tweets
  │                              │
  │                              └─ Trigger evaluate-tweet ──────► Evaluate tweet
  │                                    │                          Generate reply
  │                                    │                              │
  │                                    ├─ Store axiom_evaluation ◄────┘
  │                                    └─ Store draft_response
  │                            
Review drafts in dashboard     
  ├─ Approve / edit / reject   
  └─ Copy and post manually    
```

## Quick Start

### 1. Set Up Supabase

1. Create a [Supabase project](https://supabase.com/dashboard) (free tier works).
2. Run the base schema in the SQL Editor:
   - `src/resonance_alignment/storage/supabase_schema.sql`
3. Run the Twitter agent schema:
   - `supabase/migrations/001_twitter_agent.sql`
4. Note your **Project URL** and **anon key** (Settings → API).

### 2. Deploy Edge Functions

Install the [Supabase CLI](https://supabase.com/docs/guides/cli):

```bash
npm install -g supabase

# Link to your project
supabase login
supabase link --project-ref YOUR_PROJECT_REF

# Set secrets (edge functions need these)
supabase secrets set ANTHROPIC_API_KEY=sk-ant-your-key-here
## NOTE: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are auto-injected by Supabase.
## You only need to set the Anthropic key:

# Deploy both functions
supabase functions deploy ingest-tweet
supabase functions deploy evaluate-tweet
```

### 3. Install the Chrome Extension

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (toggle, top-right).
3. Click **Load unpacked** → select the `chrome-extension/` folder.
4. Click the Axiom extension icon in your toolbar.
5. Enter your **Supabase URL** and **anon key** → **Save & Connect**.

### 4. Use It

- Browse X/Twitter normally.
- You'll see a small **"Axiom"** button in each tweet's action bar (next to reply/retweet/like).
- Click it to capture the tweet → it gets evaluated via Claude → a draft reply is generated.
- You can also **right-click selected text** → "Evaluate with Axiom" for any text on X.

### 5. Review Drafts

For now, check drafts directly in Supabase:

```sql
-- View pending drafts with their evaluations
SELECT
  d.draft_text,
  d.tone,
  d.status,
  e.quadrant,
  e.quality_score,
  e.evaluation_reasoning,
  t.tweet_text,
  t.author_handle,
  t.tweet_url
FROM draft_responses d
JOIN ingested_tweets t ON d.tweet_id = t.id
LEFT JOIN axiom_evaluations e ON d.evaluation_id = e.id
WHERE d.status = 'pending'
ORDER BY d.created_at DESC;
```

A dedicated dashboard is planned for a future version.

## File Structure

```
chrome-extension/
├── manifest.json       # Extension manifest (Manifest V3)
├── background.js       # Service worker (context menu, coordination)
├── content.js          # Injected into X.com (Axiom buttons on tweets)
├── content.css         # Styles for injected UI
├── popup.html          # Extension popup (settings)
├── popup.js            # Popup logic
├── icons/              # Extension icons (16, 48, 128px)
├── generate_icons.py   # Script to regenerate icons
└── generate-icons.html # Browser-based icon generator (backup)

supabase/
├── functions/
│   ├── ingest-tweet/index.ts    # Receives tweets from extension
│   └── evaluate-tweet/index.ts  # Evaluates via Claude + generates drafts
└── migrations/
    └── 001_twitter_agent.sql    # Database schema for Twitter agent
```

## Cost

- **Supabase Free Tier**: 500MB database, 500K edge function invocations/month — more than enough.
- **Claude Sonnet**: ~$0.003 per tweet (evaluation + draft) → ~$3 per 1,000 tweets.
- **Total**: Effectively just Claude API costs. If you evaluate 50 tweets/day, that's ~$4.50/month.

## Security Notes

- The Chrome extension stores your Supabase **anon key** (not the service role key).
- Edge functions use the **service role key** (set as a Supabase secret, never exposed to the client).
- The anon key can only insert into `ingested_tweets` — consider adding RLS policies for production:

```sql
-- Example: allow inserts only, no reads from anon
ALTER TABLE ingested_tweets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anonymous inserts" ON ingested_tweets
  FOR INSERT TO anon WITH CHECK (true);
```
