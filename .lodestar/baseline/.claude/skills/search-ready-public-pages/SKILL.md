---
name: search-ready-public-pages
description: Use when building, changing or launching any public landing page, marketing site, blog or public web page, including one built in Bubble or another no-code tool. The search checklist - each page's own title, description and one heading, structured data that matches the page, FAQs and their schema, the sitemap and robots.txt, real links, image alt text, noindex for dead and in-house pages, mobile speed, and the accounts to sort out before launch (who owns the domain, Search Console, Bing, IndexNow). Pairs with agent-ready-public-pages.
---

# Search-ready public pages

A search engine ranks what it can read, quickly, on a phone. This is the checklist for any public
page, in code or in a no-code builder like Bubble, in every project Lodestar reaches. Three projects
did this same work on their own: MSC's search-data test (16 Sep 2026), Whitespace's landing pass
(15 Oct 2026) and Quiz2Coin's fixes in Bubble (18 Nov 2026). This is what they agree on.

## Every page

1. **Its own title and description.** Title 10–90 characters, description 50–180. No two pages share
   either. A page built from a template takes them from its data: "[quiz] Quiz: Play Free on Quiz2Coin".
2. **One H1 that says what the page is**, then H2s for its sections. A slogan is not an H1.
3. **One address per page.** A canonical link on every page; one host (www goes to the bare domain, or
   the reverse); tracking copies like `?ref=` point at the clean address. A translated page points at
   itself and lists the others with `hreflang`.
4. **A share card:** `og:title`, `og:description` and `og:image`.
5. **Alt text on every image that means something.** Generated cards take it from their data (the quiz
   name). Decoration gets `alt=""`.
6. **Anything that goes to another page is a real link** (`<a href>`), so a crawler can follow it. The
   one exception is a button that must run a check first (eligibility, a replay rule); write down why.
7. **Pinch-zoom works.** No `user-scalable=no`, no `maximum-scale=1`.

## Structured data (JSON-LD)

- **Homepage:** `Organization` (name, logo, and `sameAs` listing only the profiles the site really links
  to) and `WebSite`. An app adds `MobileApplication` with its real prices. A blog post adds `Article` with
  its real date.
- **A script writes the head block between markers** (`<!-- seo:begin -->` … `<!-- seo:end -->`), so
  running it again replaces the block instead of adding a second copy.
- **Check it with Google's Rich Results Test.** That also shows whether Google can render a page built
  by JavaScript. If it can, no prerender service is needed.

## FAQs

An FAQ is where a site answers the questions people type into search and ask assistants.

- **One list feeds both the visible FAQ and its `FAQPage` schema**, so the two can't drift. MSC renders
  its accordion and its schema from one data file; Whitespace's script reads the schema out of the
  visible FAQ. A translated page whose schema isn't translated drops it.
- **The answers are in the HTML**, even when the FAQ is shown folded. An answer that loads on a click
  is not read.
- **Ask it the way a customer would, and answer in the first sentence.** The detail follows.
- **A guide or article with its own questions gets its own FAQ and schema** (MSC's resource pages).
- Google now shows FAQ rich results only for a few authority sites, so the schema's payoff is answer
  engines and AI assistants reading it, not a bigger search listing. It is still worth doing.

## The sitemap

- **Built from an allow-list, by a script, on every build.** A page is in it because someone named it,
  or because it is a published post, never because a glob found it. Whitespace names its pages in
  `build-sitemap.mjs` and adds blog posts; MSC names its pages in `app/sitemap.js` and adds its articles.
- **Never in it:** utility pages (404, reset password, sign-in, create-a-quiz), the app, previews, drafts,
  and any page that sends `noindex`.
- **Every address in it loads with a 200, on the canonical host,** with no redirect in between.
- **`lastmod` is the date the page really changed**, from git or the post's own date. Stamping every page
  with the build time teaches Google to ignore the field. Google ignores `priority` and `changefreq`.
- **Translations are listed with `hreflang` alternates** in the sitemap as well as in the page.

## robots.txt

- **Disallow whole folders where nothing is public:** the app, `/api/`, sign-in, admin (MSC: `/dashboard`,
  `/onboarding`, `/api/`, `/auth/`; Nothing Unwanted: `/admin`). End with the `Sitemap:` line.
- **Hide a private page with `noindex`, not with robots.txt.** A disallowed page is never fetched, so
  its `noindex` is never seen, and its bare address can still show in results. robots.txt is also
  public: a line per private page hands anyone the list of them.
- **The AI-use policy and AI crawler rules** are in agent-ready-public-pages.

## What stays out of search

- **A dead or expired page sends `noindex`** (a finished quiz, a removed article), not a "not found"
  message with a 200.
- **In-house pages send `X-Robots-Tag: noindex`:** the app, previews, mocks, campaign pages.
- **Policy pages the site links to live on the site's own domain** (cookies, privacy, terms).

## Mobile speed

Measure with Lighthouse on mobile and slow 4G, before and after, and put both numbers in the change.

- **Heavy libraries load when someone needs them, not for every visitor.** Quiz2Coin's sign-in wallet
  library now loads on Log In, and the page went from 11.8 MB to 5.6 MB.
- **Hold space for anything that arrives late** (banners, sliders), so the page doesn't jump. Quiz2Coin's
  layout shift went from 0.36 to 0.007.
- **No debug tools on a live page.** A debug console had shipped inside a slider.
- **Each tracking tag loads once.** Quiz2Coin had two tag managers, two analytics tags and two of each ad
  pixel. Ad pixels go through the tag manager and fire after cookie consent.
- **Fonts are licensed for the web.** Apple's SF Pro isn't; use a free one such as Inter.

## Say only what is true

Titles, descriptions, structured data and share cards say what the product does today. When Quiz2Coin
dropped NFTs, the word came out of the site and its social descriptions the same day. Wording left inside
banner images went on marketing's list, by name.

## Before launch: who owns the domain

Quiz2Coin's Search Console, sitemap submission and redirects all stalled on a DNS account nobody on the
team could reach. Settle these before they're needed:

1. **Name the DNS host and the person who can change it.**
2. **Verify a Search Console domain property** (a DNS TXT record). If a verification record is already
   there, find its owner: they can add you without touching DNS.
3. **Submit the sitemap**, and link Search Console to the analytics property.
4. **Add Bing Webmaster Tools** by importing from Search Console. Bing's index is what ChatGPT search
   reads.
5. **Set up IndexNow:** a key file at the site root and a script that sends the sitemap after each deploy,
   so new and changed pages are found in days rather than weeks.

## Keep it true with a test

Run a check on every build that reads the live sitemap and, for each page, checks title and description
length, duplicates, `og:title`, exactly one H1, JSON-LD that parses, and links that land. It also checks
that every sitemap address loads, and that robots.txt disallows the app and names the sitemap. Problems that
were already live when the test arrived go in a named list so they don't fail every run. Fixing one fails
the test until its line is removed, so the list only ever shrinks.

## Provenance

- **MSC** (MSC-DEV-40, 16 Sep 2026): `e2e/seo.spec.ts`, the search-data test and its known-issues list;
  `app/sitemap.js`, `app/robots.js`, and `data/homepageFaqs.js` feeding both `FAQAccordion` and `FAQSchema`.
- **Whitespace landing** (15 Oct 2026): `scripts/seo-head.py` (canonical, hreflang, JSON-LD between
  markers, FAQ schema read from the visible FAQ), `scripts/build-sitemap.mjs` (allow-list, git `lastmod`,
  hreflang), `scripts/indexnow.mjs`, noindex headers in `vercel.json`, the www redirect.
- **One2all** (28 Oct 2026) and **Nothing Unwanted**: `public/robots.txt` and `public/sitemap.xml`.
- **Quiz2Coin** (18 Nov 2026, in Bubble, from Thomas's SEO report): `docs/seo-report-status-2026-11-18.md`
  on chusla/quiz2coin, fixes B1–B14 and the DNS blockers.
- **Andrew, 19 Nov 2026:** "the SEO enhancements for quiz2coin are quite good for general use as an
  example".

Related: agent-ready-public-pages (the same pages, for AI assistants), zid-proof (the words) and
kelly-proof (the composition).
