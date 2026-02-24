# Prompts

Canonical source of truth for all Arete and Axiom system prompts. These files
are synced to the Supabase `system_prompts` table via the push script and
fetched at runtime by edge functions.

## Files

| File | Slug | Used By |
|------|------|---------|
| `evaluation.md` | `arete.evaluation` | Tweet evaluation pass (Axiom scoring) |
| `arete-short.md` | `arete.short` | Draft response in short/tweet mode (≤260 chars) |
| `arete-long.md` | `arete.long` | Draft response in long/thread mode (600–4000 chars) |

## Editing Prompts

1. Edit the relevant `.md` file directly
2. Push to Supabase:
   ```
   deno run --allow-env --allow-net --allow-read scripts/prompts-push.ts
   ```
3. No code deploy needed — the edge function fetches from DB at runtime

Dry-run to preview what will be pushed:
```
deno run --allow-env --allow-net --allow-read scripts/prompts-push.ts --dry-run
```

## Runtime Behavior

The `evaluate-tweet` edge function fetches all three prompts from
`system_prompts` at the start of each invocation. Results are cached
in module scope for the lifetime of the edge function instance (warm calls
skip the DB fetch).

If a prompt is missing from the DB, the function throws and the request fails —
there are no hardcoded fallbacks. Run the push script after any schema reset.
