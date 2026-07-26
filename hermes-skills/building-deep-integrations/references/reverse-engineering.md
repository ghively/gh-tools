# Reverse-engineering undocumented APIs from real UI traffic

Use this when an API is registered but no guessed `method`/`params` works, or when a
feature has no public API docs. Instead of guessing, watch the vendor's own web UI make
the call and copy it exactly. This is how the Synology Hyper Backup / Active Backup APIs
were cracked after blind fuzzing failed.

## Why guessing fails and this doesn't

Blind method fuzzing misses because the real call differs from your guess in ways you
can't enumerate: a different entity name (`SYNO.ActiveBackup.Device`, not `.Task`), a
required structural param (`node:"module_root"`), and a non-max version (`v1`). The UI
already knows all three. Capture, don't guess.

## The workflow

1. **Get a browser onto the system's UI.** Use browser automation (a Claude browser
   extension, or Playwright). Log in — if a password must be typed to authenticate,
   have the **user** do that step (entering passwords to authenticate is theirs to do);
   you drive everything after.

2. **Inject a network interceptor** into the page before triggering the feature. It
   records every API call's endpoint, method, version, and params into a global array.
   Generic XHR-based version (works for most webapi-style backends):

   ```js
   (function(){
     if (window.__cap) return "already";
     window.__cap = [];
     const parse = b => { try { const o={}, p=new URLSearchParams(b);
       for (const [k,v] of p) o[k]=v.length>300?v.slice(0,300)+'…':v; return o; }
       catch(e){ return String(b).slice(0,300); } };
     const O=XMLHttpRequest.prototype.open, S=XMLHttpRequest.prototype.send;
     XMLHttpRequest.prototype.open=function(m,u){ this.__u=u; return O.apply(this,arguments); };
     XMLHttpRequest.prototype.send=function(b){
       try{
         if(this.__u && this.__u.includes('.cgi')){       // adjust to the backend's API path
           const body=parse(b), q={};
           try{ new URL(this.__u,location.origin).searchParams.forEach((v,k)=>q[k]=v);}catch(e){}
           const api=(body&&body.api)||q.api;
           if(api) window.__cap.push({api, method:(body&&body.method)||q.method,
                                      version:(body&&body.version)||q.version, params: body||q});
         }
       }catch(e){}
       return S.apply(this,arguments);
     };
     return "installed";
   })();
   ```

   If the app uses `fetch()` instead of `XMLHttpRequest`, wrap `window.fetch` the same
   way. If it batches calls (a "compound"/"batch" request), the individual calls are in
   the POST body — the interceptor above already captures the body.

3. **Click the exact feature** you want to replicate (the list view, the detail pane,
   the action button — but NOT a destructive action you don't intend to run).

4. **Dump the capture** — the unique `api::method vN` plus param keys:

   ```js
   JSON.stringify([...new Map((window.__cap||[])
     .map(c=>[c.api+'::'+c.method+' v'+c.version, c.params])).entries()], null, 1)
   ```

5. **Replay from your client** to confirm it works headless, then build the curated
   tool around the verified shape. If it works in the browser but 102s from your client,
   the API is session/context-gated — note it (it may need the app "open", which a
   standalone client can't do).

## Safety

- Capture reads freely. Do **not** click "Back up now", "Delete", "Apply", etc. just to
  capture their call — that runs the real action. To wire a write you must trigger once,
  get the user's explicit go-ahead on a specific target first.
- You are reading the user's own system's traffic to integrate with it — legitimate. Do
  not exfiltrate captured tokens; keep them in-page.

## Non-browser fallbacks (try first when cheap)

- **Discovery/OpenAPI docs**, a `--help`/`--list` on a CLI, or the system's own SDK.
- **Fuzz a method dictionary** against the target API with safe params (`list`, `get`,
  `enum`, `load`, `list_*`, `get_*`, …) — cheap, and sometimes enough. But if it comes
  up empty, escalate to UI capture rather than concluding "not possible."
