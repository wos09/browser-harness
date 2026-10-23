---
name: browser
description: Direct browser control via CDP. Use when the user wants to automate, scrape, test, or interact with web pages. Connects to the user's already-running Chrome.
---

# browser-harness

Direct browser control via CDP. For task-specific edits, use `agent-workspace/agent_helpers.py`. For setup, install, or connection problems, read install.md.

Domain skills (community-contributed per-site playbooks under `agent-workspace/domain-skills/`) are off by default. Set `BH_DOMAIN_SKILLS=1` to enable them; see the bottom section.

**If `BH_DOMAIN_SKILLS=1` and the task is site-specific, read every file in the matching `agent-workspace/domain-skills/<site>/` directory before inventing an approach.**

## Usage

```bash
browser-harness <<'PY'
new_tab("https://docs.browser-use.com")
wait_for_load()
print(page_info())
PY
```

- Invoke as browser-harness — it's on $PATH. No cd, no uv run.
- Use the heredoc form for every multi-line command. It prevents shell quote mangling inside Python strings and JavaScript snippets.
- First navigation is new_tab(url), not goto_url(url) — goto runs in the user's active tab and clobbers their work.

## Tool call shape

```bash
browser-harness <<'PY'
# any python. helpers pre-imported. daemon auto-starts.
PY
```

run.py calls ensure_daemon() before exec — you never start/stop manually unless you want to.

### Remote browsers

Use remote for parallel sub-agents (each gets its own isolated browser via a distinct BU_NAME) or on a headless server. BROWSER_USE_API_KEY must be set. start_remote_daemon, list_cloud_profiles, list_local_profiles, sync_local_profile are pre-imported.

```bash
browser-harness <<'PY'
start_remote_daemon("work")                               # default — clean browser, no profile
# start_remote_daemon("work", profileName="my-work")      # reuse a cloud profile (already logged in)
# start_remote_daemon("work", profileId="<uuid>")         # same, but by UUID
# start_remote_daemon("work", proxyCountryCode="de", timeout=120)   # DE proxy, 2-hour timeout
# start_remote_daemon("work", proxyCountryCode=None)      # disable the Browser Use proxy
PY

BU_NAME=work browser-harness <<'PY'
new_tab("https://example.com")
print(page_info())
PY
```

start_remote_daemon prints liveUrl and auto-opens it in the local browser (if a GUI is detected) so the user can watch along. Headless servers print only — share the URL with the user. The daemon PATCHes the cloud browser to stop on shutdown, which persists profile state. Running remote daemons bill until timeout.

Profiles (cookies-only login state) live in interaction-skills/profile-sync.md — covers list_cloud_profiles(), the chat-driven "which profile?" pattern, and sync_local_profile() for uploading a local Chrome profile.

## Interaction skills

If you start struggling with a specific mechanic while navigating, look in interaction-skills/ for helpers. They cover reusable UI mechanics like dialogs, tabs, dropdowns, iframes, and uploads. The available interaction skills are:
- connection.md
- cookies.md
- cross-origin-iframes.md
- dialogs.md
- downloads.md
- drag-and-drop.md
- dropdowns.md
- iframes.md
- network-requests.md
- print-as-pdf.md
- profile-sync.md
- screenshots.md
- scrolling.md
- shadow-dom.md
- tabs.md
- uploads.md
- viewport.md

## What actually works

**DOM first, screenshot last.** A screenshot round trip costs seconds and thousands of tokens; reading the DOM costs milliseconds. The helpers in `agent-workspace/agent_helpers.py` (pre-imported) are the default way to drive a page:

```bash
browser-harness <<'PY'
new_tab("https://example.com/form"); wait_for_load()
snapshot()                      # numbered list of buttons/links/inputs/selects, with values and state
act(                            # several actions in ONE call; prints a fresh snapshot at the end
  ("fill", "Name", "Maria"),    # by label/placeholder/name (string) or by ref (int)
  ("select", "State", "CA"),
  ("click", "Agree"),
  ("click", "Save"),
)
print(read(grep="success|error"))  # visible text, filtered by regex
PY
```

- `snapshot()` first on every new page. Modals are detected and listed alone. Elements below the fold are tagged and scrolled into view on click.
- `click_text("Save")`, `fill_label("Email", "x@y.com")`, `click_ref(12)`, `fill_ref(3, "...")`, `select_ref(7, "Option")` for single actions; `act(...)` to chain them. Prefer names (strings) inside `act`, they are re-resolved at each step; int refs go stale when the DOM changes (use `("snap",)` to renumber).
- Warnings like `# warning: 2 elements match` mean ambiguous text: pass `nth=` or a ref.
- Repeated names (a "Delete" or checkbox per list row) are shown as `in row "<row text>"`: pick the right one by its ref. `("dblclick", ...)` / `click_text(..., clicks=2)` double-click, e.g. to start inline editing. Custom checkboxes hidden at opacity 0 are listed too.
- Put the verification in the same call (`read(grep=...)`, `page_info()`, `js(...)` returning the value you care about) instead of taking a screenshot.
- Take `capture_screenshot()` only when: the snapshot shows an iframe/canvas you cannot read, the result is visual (layout, colors, image), a click had no effect and the DOM does not explain why, or the user asked to see it.
- Coordinate clicking (`click_at_xy`) is the fallback for canvas, iframes and elements the snapshot cannot see. Hit-testing happens in Chrome's browser process, so clicks go through iframes / shadow DOM / cross-origin.
- Bulk HTTP: http_get(url) + ThreadPoolExecutor. No browser for static pages (249 Netflix pages in 2.8s). If the page loads data from an API, find it with interaction-skills/network-requests.md and call it directly.
- After goto: wait_for_load(). `act`/`click_*` already settle after each step.
- Wrong/stale tab: ensure_real_tab(). Use it when the current tab is stale or internal; the daemon also auto-recovers from stale sessions on the next call.
- DOM reads beyond the snapshot: use js(...) for inspection and extraction.
- Auth wall: redirected to login → stop and ask the user. Don't type credentials from screenshots.
- Raw CDP for anything helpers don't cover: cdp("Domain.method", params).

## Design constraints

- DOM refs by default (snapshot/act); clicks are still real CDP Input events. Coordinate clicks are the fallback for canvas/iframes.
- Connect to the user's running Chrome. Don't launch your own browser.
- cdp-use is only for CDPClient.send_raw. Prefer raw CDP strings over typed wrappers.
- run.py stays tiny. No argparse, subcommands, or extra control layer.
- Core helpers stay short. Put task-specific helper additions in `agent-workspace/agent_helpers.py`; daemon/bootstrap and remote session admin live in the core package.
- Don't add a manager layer. No retries framework, session manager, daemon supervisor, config system, or logging framework.

## Gotchas (field-tested)

- Omnibox popups are fake page targets. Filter chrome://omnibox-popup... and other internals when you need a real tab.
- CDP target order != Chrome's visible tab-strip order. Use UI automation when the user means "the first/second tab I can see"; Target.activateTarget only shows a known target.
- Default daemon sessions can go stale. ensure_real_tab() re-attaches to a real page.
- Browser Use API is camelCase on the wire. cdpUrl, proxyCountryCode, etc.
- Remote cdpUrl is HTTPS, not ws. Resolve the websocket URL via /json/version.
- Stop cloud browsers with PATCH /browsers/{id} + {"action":"stop"}.
- After every meaningful action, verify through the DOM in the same call (`act` ends with a snapshot; add `read(grep=...)` or `page_info()` for success/error text). Screenshot only when the check is visual.
- Explore with `snapshot()` and `read()`, not screenshots. Fall back to a screenshot when the snapshot cannot explain what you see (canvas, iframe, overlay).
- Prefer `click_ref`/`click_text` (real CDP mouse events at the element's center) over framework hacks. If a control ignores them, try coordinate clicks and raw key input before DOM-specific workarounds.
- If you need framework-specific DOM tricks, check interaction-skills/ first. That is where dropdown, dialog, iframe, shadow DOM, and form-specific guidance belongs.

## Domain skills (opt-in)

Only applies when `BH_DOMAIN_SKILLS=1`. Otherwise ignore — `agent-workspace/domain-skills/` is dormant and `goto_url` won't surface skill files.

When enabled, search `agent-workspace/domain-skills/<host>/` before inventing an approach. `goto_url` returns up to 10 skill filenames for the navigated host.

If you learn anything non-obvious — a private API, stable selector, framework quirk, URL pattern, hidden wait, or site-specific trap — open a PR to `agent-workspace/domain-skills/<site>/`. Capture the durable shape of the site (the map, not the diary). Don't write pixel coordinates (break on layout), task narration, or secrets — the directory is public.
