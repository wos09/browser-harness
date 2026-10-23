"""Agent-editable browser helpers.

Add task-specific browser primitives here. Core helpers from browser_harness.helpers
load this file when BH_AGENT_WORKSPACE points at this directory, or when this
repo's default agent-workspace exists.

DOM-first layer: snapshot() lists the interactive elements as numbered refs, and
click_ref / fill_ref / click_text / fill_label / act act on them without screenshots.
Clicks still go through CDP Input events (trusted), so they behave like a real user.
"""
import json as _json
import time as _time


def _h():
    from browser_harness import helpers
    return helpers


_SNAPSHOT_JS = r"""
(() => {
  const INTER = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],' +
    '[role=checkbox],[role=radio],[role=switch],[role=tab],[role=menuitem],[role=option],[role=combobox],' +
    '[role=textbox],[role=searchbox],[role=menuitemcheckbox],[contenteditable=""],[contenteditable=true],' +
    '[tabindex]:not([tabindex="-1"]),[onclick]';
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const deep = (root, sel, out = []) => {
    root.querySelectorAll(sel).forEach(e => out.push(e));
    root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) deep(e.shadowRoot, sel, out); });
    return out;
  };
  const visible = e => {
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const cs = getComputedStyle(e);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  };
  const labelOf = e => {
    const ids = e.getAttribute('aria-labelledby');
    if (ids) { const t = ids.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(x => x.innerText).join(' '); if (norm(t)) return norm(t); }
    if (e.getAttribute('aria-label')) return norm(e.getAttribute('aria-label'));
    if (e.labels && e.labels.length) return norm([...e.labels].map(l => l.innerText).join(' '));
    const wrap = e.closest('label'); if (wrap) return norm(wrap.innerText);
    return '';
  };
  const roleOf = e => {
    const r = e.getAttribute('role'); if (r) return r;
    const t = e.tagName.toLowerCase();
    if (t === 'a') return 'link';
    if (t === 'select') return 'select';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      const ty = (e.type || 'text').toLowerCase();
      if (ty === 'checkbox' || ty === 'radio') return ty;
      if (['submit', 'button', 'reset', 'image'].includes(ty)) return 'button';
      return 'textbox';
    }
    if (t === 'button' || t === 'summary') return 'button';
    if (e.isContentEditable) return 'textbox';
    return 'clickable';
  };
  const nameOf = e => {
    let n = labelOf(e);
    if (!n && /^(INPUT|TEXTAREA)$/.test(e.tagName)) {
      if (['submit', 'button', 'reset'].includes(e.type)) n = e.value;
      n = n || e.placeholder || e.getAttribute('title') || e.name || '';
    }
    if (!n && e.tagName === 'SELECT') n = e.name || e.getAttribute('title') || '';
    if (!n) n = e.innerText || e.getAttribute('title') || e.getAttribute('alt') || '';
    if (!n) { const img = e.querySelector('img[alt],svg title'); if (img) n = img.getAttribute('alt') || img.textContent; }
    if (!n) n = e.getAttribute('placeholder') || e.getAttribute('data-testid') || '';
    return norm(n).slice(0, 80);
  };

  // a modal only counts if it is actually on screen (sites keep off-canvas role=dialog nav panels around)
  const onScreen = e => {
    const r = e.getBoundingClientRect();
    const w = Math.min(r.right, innerWidth) - Math.max(r.left, 0), h = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
    return w > 0 && h > 0 && (w * h) / (r.width * r.height) > 0.5;
  };
  const dialogs = deep(document, 'dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]').filter(e => visible(e) && onScreen(e));
  const modal = dialogs.length ? dialogs[dialogs.length - 1] : null;

  let els = deep(document, INTER).filter(visible);
  els = els.filter((e, i) => els.indexOf(e) === i);
  if (modal) els = els.filter(e => modal.contains(e));

  window.__bh = [];
  const vh = innerHeight, vw = innerWidth;
  const items = els.map(e => {
    const r = e.getBoundingClientRect();
    const o = { role: roleOf(e), name: nameOf(e) };
    if (e.tagName === 'A' && e.getAttribute('href')) o.href = e.getAttribute('href').slice(0, 70);
    if (e.tagName === 'SELECT') o.value = (e.selectedOptions[0] ? e.selectedOptions[0].text : '') + ' [' + e.options.length + ' opts]';
    else if (/^(INPUT|TEXTAREA)$/.test(e.tagName) && !['checkbox', 'radio', 'submit', 'button'].includes(e.type)) o.value = (e.value || '').slice(0, 50);
    else if (e.isContentEditable) o.value = norm(e.innerText).slice(0, 50);
    if (e.type === 'checkbox' || e.type === 'radio') o.checked = e.checked;
    else if (e.getAttribute('aria-checked') != null) o.checked = e.getAttribute('aria-checked') === 'true';
    if (e.disabled || e.getAttribute('aria-disabled') === 'true') o.disabled = true;
    if (e.getAttribute('aria-expanded') != null) o.expanded = e.getAttribute('aria-expanded') === 'true';
    if (e.getAttribute('aria-selected') === 'true' || e.getAttribute('aria-current')) o.selected = true;
    if (e.required) o.required = true;
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) o.off = r.top > vh ? 'below' : (r.bottom < 0 ? 'above' : 'side');
    return { o, e };
  });
  items.forEach(({ e }) => window.__bh.push(e));

  const heads = deep(document, 'h1,h2,h3').filter(visible).slice(0, 8).map(h => norm(h.innerText).slice(0, 70)).filter(Boolean);
  const frames = [...document.querySelectorAll('iframe')].filter(visible).map(f => (f.src || '').slice(0, 70));
  return JSON.stringify({
    url: location.href, title: document.title, heads, frames,
    modal: modal ? norm(modal.getAttribute('aria-label') || (modal.querySelector('h1,h2,h3') || {}).innerText || 'dialog').slice(0, 60) : null,
    items: items.map(x => x.o),
  });
})()
"""


def _fmt(i, o):
    flags = []
    if "checked" in o:
        flags.append("checked" if o["checked"] else "unchecked")
    for k in ("disabled", "expanded", "selected", "required"):
        if o.get(k):
            flags.append(k)
    s = f'[{i}] {o["role"]} "{o["name"]}"'
    if "value" in o:
        s += f' = "{o["value"]}"'
    if o.get("href"):
        s += f' -> {o["href"]}'
    if flags:
        s += " (" + ", ".join(flags) + ")"
    if o.get("off"):
        s += f' [{o["off"]} viewport]'
    return s


def snapshot(limit=120, show=True):
    """List the interactive elements of the current tab as numbered refs.

    Re-run after any navigation or large DOM change: refs are positions in the last snapshot.
    If a modal/dialog is open, only its contents are listed. Elements outside the viewport
    are tagged [below viewport] etc.; click_ref scrolls to them automatically.
    """
    d = _json.loads(_h().js(_SNAPSHOT_JS))
    if show:
        print(f'# {d["title"]} | {d["url"]}')
        if d["modal"]:
            print(f'# MODAL open: {d["modal"]} (only its elements are listed)')
        if d["heads"]:
            print("# headings: " + " | ".join(d["heads"]))
        if d["frames"]:
            print(f'# {len(d["frames"])} visible iframe(s) (contents not listed; use iframe_target or a screenshot): ' + ", ".join(d["frames"][:3]))
        shown = [(i, o) for i, o in enumerate(d["items"]) if o.get("off") != "side"]  # off-canvas panels are unreachable noise
        for i, o in shown[:limit]:
            print(_fmt(i, o))
        if len(shown) > limit:
            print(f'# ... +{len(shown) - limit} more elements (raise limit= or use click_text)')
    return d


def _center(n):
    r = _h().js(
        "(()=>{const e=(window.__bh||[])[%d];if(!e||!e.isConnected)return null;"
        "e.scrollIntoView({block:'center',inline:'center'});const r=e.getBoundingClientRect();"
        "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % n
    )
    if not r:
        raise RuntimeError(f"ref [{n}] is stale; run snapshot() again")
    return _json.loads(r)


def settle(timeout=4.0):
    """Wait for the page to finish loading after an action (cheap when nothing is loading)."""
    _time.sleep(0.25)
    _h().wait_for_load(timeout)


def click_ref(n, button="left", clicks=1):
    """Click the element with ref n from the last snapshot()."""
    c = _center(n)
    _h().click_at_xy(c["x"], c["y"], button=button, clicks=clicks)


def fill_ref(n, text, submit=False):
    """Replace the value of input/textarea/contenteditable ref n. Fires input+change (works with React/Vue)."""
    ok = _h().js(
        "(()=>{const e=(window.__bh||[])[%d];if(!e||!e.isConnected)return 'stale';"
        "e.scrollIntoView({block:'center'});e.focus();const t=%s;"
        "if(e.isContentEditable){document.execCommand('selectAll');document.execCommand('insertText',false,t);return 'ok';}"
        "if(e.tagName!=='INPUT'&&e.tagName!=='TEXTAREA')return 'not-text';"
        "const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "Object.getOwnPropertyDescriptor(proto,'value').set.call(e,t);"
        "e.dispatchEvent(new Event('input',{bubbles:true}));"
        "e.dispatchEvent(new Event('change',{bubbles:true}));return 'ok';})()" % (n, _json.dumps(text))
    )
    if ok == "stale":
        raise RuntimeError(f"ref [{n}] is stale; run snapshot() again")
    if ok == "not-text":
        raise RuntimeError(f"ref [{n}] is not a text field (use select_ref or click_ref)")
    if submit:
        _h().press_key("Enter")
        settle()


def select_ref(n, option):
    """Choose an <option> of <select> ref n by visible text or value (case-insensitive, substring ok)."""
    r = _h().js(
        "(()=>{const e=(window.__bh||[])[%d];if(!e||!e.isConnected||e.tagName!=='SELECT')return null;"
        "const q=%s.toLowerCase();const o=[...e.options];"
        "const m=o.find(x=>x.text.trim().toLowerCase()===q||x.value.toLowerCase()===q)||o.find(x=>x.text.toLowerCase().includes(q));"
        "if(!m)return JSON.stringify({err:o.map(x=>x.text.trim()).slice(0,30)});"
        "e.value=m.value;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));"
        "return JSON.stringify({ok:m.text.trim()});})()" % (n, _json.dumps(option))
    )
    if not r:
        raise RuntimeError(f"ref [{n}] is not a valid <select>; for a custom dropdown use click_ref + click_text")
    d = _json.loads(r)
    if "err" in d:
        raise RuntimeError(f"option {option!r} not found. Options: {d['err']}")
    return d["ok"]


def _norm(s):
    return " ".join((s or "").split()).casefold()


def _find(text, roles=None, nth=0, snap=None):
    """Return (index, item) of the interactive element whose name matches text.
    Exact matches win over substring matches; roles restricts to those roles."""
    d = snap or snapshot(show=False)
    q = _norm(text)
    cand = [(i, o) for i, o in enumerate(d["items"]) if (not roles or o["role"] in roles) and not o.get("disabled")]
    exact = [(i, o) for i, o in cand if _norm(o["name"]) == q]
    part = [(i, o) for i, o in cand if q in _norm(o["name"]) or q in _norm(o.get("value", ""))]
    # among substring matches: names that start with the query first, then the shortest name
    part.sort(key=lambda p: (not _norm(p[1]["name"]).startswith(q), len(p[1]["name"])))
    hits = exact or part
    if not hits:
        names = [o["name"] for _, o in cand if o["name"]][:25]
        raise RuntimeError(f"nothing matches {text!r}. Available elements: {names}")
    if len(hits) > 1 and nth == 0:
        print(f"# warning: {len(hits)} elements match {text!r}: " + "; ".join(_fmt(i, o) for i, o in hits[:5]) + " (using the first; pass nth=)")
    return hits[min(nth, len(hits) - 1)]


def click_text(text, nth=0, roles=None):
    """Click the interactive element whose accessible name matches text (e.g. click_text('Save')).
    Falls back to any visible element containing that text if no interactive one matches."""
    d = snapshot(show=False)
    try:
        i, o = _find(text, roles, nth, d)
    except RuntimeError as err:
        r = _h().js(
            "(()=>{const q=%s.toLowerCase();const w=document.createTreeWalker(document.body,NodeFilter.SHOW_ELEMENT);"
            "let best=null;while(w.nextNode()){const e=w.currentNode;"
            "const t=(e.innerText||'').replace(/\\s+/g,' ').trim().toLowerCase();const r=e.getBoundingClientRect();"
            "if(t.includes(q)&&r.width>0&&r.height>0&&(!best||t.length<best.t.length))best={e,t};}"
            "if(!best)return null;best.e.scrollIntoView({block:'center'});const r=best.e.getBoundingClientRect();"
            "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % _json.dumps(text)
        )
        if not r:
            raise err
        c = _json.loads(r)
        _h().click_at_xy(c["x"], c["y"])
        return f"(loose text) {text}"
    click_ref(i)
    return _fmt(i, o)


def fill_label(label, text, nth=0, submit=False):
    """Fill the text field whose label/placeholder/name matches `label`."""
    i, o = _find(label, roles={"textbox", "searchbox", "combobox"}, nth=nth)
    fill_ref(i, text, submit=submit)
    return _fmt(i, o)


def read(selector=None, grep=None, limit=3000):
    """Visible text of the page (or of a CSS selector). grep='regex' keeps only matching lines."""
    t = _h().js(
        "(()=>{const e=%s?document.querySelector(%s):document.body;return e?e.innerText:null;})()"
        % (_json.dumps(selector), _json.dumps(selector))
    )
    if t is None:
        raise RuntimeError(f"selector matched nothing: {selector}")
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    if grep:
        import re
        lines = [l for l in lines if re.search(grep, l, re.I)]
    out = "\n".join(lines)
    return out[:limit] + (f"\n# ... truncated ({len(out)} chars)" if len(out) > limit else "")


def act(*steps, snap=True, delay=0.0):
    """Run several actions in ONE call, settle after each, then print a fresh snapshot.

    Steps (tuples; an int means a ref from the last snapshot, a str means a name):
      ("goto", url)            ("click", "Save" | 12)       ("fill", "Name" | 5, "text")
      ("submit", "Search", "text")  fill + Enter             ("select", 7, "Option")
      ("key", "Enter")         ("wait", 1.5)                  ("text", "regex")  -> print matching lines
      ("snap",)                refresh the ref numbers mid-batch (do this after the DOM changes)
    Stops at the first failing step and says which one. Refs go stale after DOM changes:
    prefer names (strings) inside a batch, they are re-resolved at each step.
    """
    h = _h()
    for k, st in enumerate(steps):
        op, args = st[0], st[1:]
        try:
            if op == "goto":
                h.goto_url(args[0]); settle(10)
            elif op == "click":
                if isinstance(args[0], int): click_ref(args[0])
                else: click_text(args[0], *(args[1:2] or [0]))
                settle()
            elif op == "fill":
                if isinstance(args[0], int): fill_ref(args[0], args[1])
                else: fill_label(args[0], args[1])
            elif op == "submit":
                if isinstance(args[0], int): fill_ref(args[0], args[1], submit=True)
                else: fill_label(args[0], args[1], submit=True)
            elif op == "select":
                i = args[0] if isinstance(args[0], int) else _find(args[0], roles={"select", "combobox"})[0]
                select_ref(i, args[1])
            elif op == "key":
                h.press_key(args[0]); settle()
            elif op == "wait":
                _time.sleep(args[0])
            elif op == "text":
                print(read(grep=args[0]))
            elif op == "snap":
                snapshot(show=False)
            else:
                raise RuntimeError(f"unknown step: {op}")
        except Exception as err:
            print(f"# ERROR at step {k} {st}: {err}")
            break
        if delay:
            _time.sleep(delay)
    if snap:
        snapshot()
