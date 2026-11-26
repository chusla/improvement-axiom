---
name: agent-ready-public-pages
description: Use when building, changing or launching any public-facing landing page, marketing site or web page. Makes it readable by AI agents and assistants (markdown on request, llms.txt, Link headers, a catalog of what you really publish) without publishing metadata for things that do not exist. Run the scan after launch.
---

# Agent-ready public pages

A public page is read by two audiences: people, and the agents and assistants that answer for them.
Both should find the same true facts. This is the checklist for any landing page or public site,
in this repo and in every project Lodestar reaches. It came from an agent-readiness scan of
trywhitespace.com on Oct 28 2026 that scored 20 out of 100, and from sorting which of its findings
were real work and which were not.

## Do these on every public site

1. **robots.txt and the sitemap follow search-ready-public-pages** (an allow-list sitemap; private
   pages hidden with `noindex`, not by naming them in robots.txt). The same allow-list feeds every
   agent file below, so no private page reaches one.
   **Where the host serves the repo folder as the site** (Vercel with no build step), every committed
   file is public at its own address, server code included: "not linked" is not "not public".
   Whitespace's `/middleware.js`, `/api/*.js`, `/vercel.json` and `.claude/` were all readable (Nov
   2026). Files the site doesn't need go in `.vercelignore`. Files the host must still read
   (`vercel.json`, middleware, `api/`) can't be ignored, so give their addresses a redirect, which the
   host applies before it serves a file. Better still, build the site into its own output folder.
2. **`/llms.txt`: a short, vetted description.** What it is, who it is for, the facts an assistant
   will be asked (platforms, languages, pricing, privacy, contact), and links to the real pages.
   **Facts that change are generated from where the product keeps them:** MSC's llms.txt builds its
   plans from the same code that charges customers, and its article list from the articles, so neither
   can drift. Whatever has no such source is written by hand and re-read at every price, feature or
   platform change.
3. **Markdown on request.** `GET` with `Accept: text/markdown` returns the page as markdown
   (`Content-Type: text/markdown`); everyone else still gets HTML. Generate it from the same allow-list
   as the sitemap. A page built by JavaScript is not scraped: its markdown is the hand-kept facts from
   llms.txt. Serve the markdown files `noindex` so they never compete with the page in search, and send
   `Vary: Accept`.
4. **`Link` response headers on the homepage** pointing agents to what exists: the markdown
   alternate, llms.txt (`describedby`), the sitemap, and the catalog below (`rel="ard"`).
5. **A catalog of what you really publish** at `/.well-known/ard.json` (Agentic Resource Discovery,
   served as `application/ai-catalog+json`): the llms.txt, the sitemap, a public guides feed, each with
   an `identifier`, a type, a URL and two to five example questions it answers. An entry with `id`
   instead of `identifier` fails as invalid. Lighthouse 13.6 scores this as "Agentic Browsing".
   `/.well-known/ai-catalog.json` counts only as the old address: serve the same file there too if you
   already published one.
6. **State the AI-use policy on purpose** with `Content-Signal` in robots.txt (`ai-train`, `search`,
   `ai-input`). It is a business decision, not a default: the owner chooses, and the choice is
   written down next to the line. If AI crawlers get different rules from search engines, name them
   in their own block (One2all lists GPTBot, ClaudeBot, PerplexityBot, Google-Extended and the rest),
   and repeat the private-folder `Disallow` lines there: a crawler with its own block ignores the `*` one.
7. **Check it after launch**, and record the result in the change: run
   `https://isitagentready.com/<domain>`, `curl -H "Accept: text/markdown" <url>`, and `curl -I <url>`
   for the Link header. Measure speed and the Lighthouse score at `https://pagespeed.web.dev`, not with
   Lighthouse on your own machine: on an ARM Windows machine its emulated Chrome scored a page 39 that
   Google scores 99. **After every deploy, try a few repo files on the live site:** `/vercel.json`,
   `/package.json`, `/README.md`, `/lodestar.lock`, `/.claude/skills/station/SKILL.md` and one file under
   `/api/` or `/scripts/`. Each must return 404 or redirect, never 200.

## Do NOT do these

- **Do not publish metadata for something that does not exist.** No API catalog, OAuth or OIDC
  discovery, MCP server card, agent-skills index, payment-protocol manifest or WebMCP tool for an
  API, auth server, MCP server or checkout the site does not have. A manifest that points at nothing
  sends an agent to a dead end and is a small lie. The score is not the goal. Publish one the day the
  thing it describes is real.
- **No contact details, prices or claims in an agent file that are not also true on the page.**
- **No internal pages in any agent file.** One slip puts a private demo in front of every assistant.
- **No hidden text or cloaking.** Agents get the same facts people get, in another format.

## Provenance

Andrew, Oct 28 2026: "improve agent readability ... add these best practices to hq for any public
facing landing or web page". Reference implementation: whitespace-landing `scripts/build-agent-markdown.mjs`,
`llms.txt`, the `agent-md/` rewrites and `Link` headers in `vercel.json`, and
`.well-known/ard.json` (moved from `ai-catalog.json` in landing PR #74, Nov 2026; it scores 4 of 4 on
mobile PageSpeed). Generated llms.txt: mysmartcoitracker `app/llms.txt/route.ts` (plans from
`lib/pricing-copy.ts`). Named AI-crawler block: one2all `public/robots.txt`.

Related: zid-proof (the words), kelly-proof (the composition). A page can pass both and still be
invisible to an agent, and the reverse.
