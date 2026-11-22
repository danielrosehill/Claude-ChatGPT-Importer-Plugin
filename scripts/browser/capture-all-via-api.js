// Batch-export every ChatGPT conversation through the web app's own backend API, from a logged-in chatgpt.com tab.
// Paste into mcp__claude-in-chrome__javascript_tool. It STARTS a background job and returns at once; poll with
//   JSON.stringify(window.__cgx.progress())
// The leading `await` is required (see capture-via-api.js).
//
// Covers, per workspace/account: the normal list, archived chats, and chats inside Projects (which the normal
// list does not return). Every account the login can see is exported unless OPTS.accounts narrows it; the
// ChatGPT-Account-Id header selects the workspace.
//
// Output: JSONL files in the browser's download directory, chatgpt-export-<run>-<NNN>.jsonl, one raw conversation
// per line (the same payload capture-via-api.js saves, plus _account_id, _source, _listed). The body never comes
// back through the tool. Normalize with normalize_conversation.py (it accepts one conversation per file; split the
// JSONL first, or use build_dataset.py).
//
// Edit OPTS before pasting. Test small first (limit: 20).
await (async () => {
  const OPTS = {
    limit: 20,            // max conversations in total (0 = all). Test with 20 first.
    chunk: 200,           // conversations per JSONL file
    concurrency: 1,       // conversation DETAIL fetches are rate-limited (see SKILL.md): stay at 1-2
    delayMs: 1500,        // per request, per worker; a 429's Retry-After is always honoured on top
    listPages: 10,        // list pages fetched in parallel (the list endpoint was not throttled)
    ids: null,            // optional priority list of conversation ids: fetch only these, in this order
    accounts: null,       // null = all accounts; or ['<account id>', ...]
    archived: true,
    projects: true,
    updatedAfter: null,   // ISO date: only conversations updated after this (incremental runs)
  };
  if (window.__cgx && window.__cgx.running) return JSON.stringify({ ok: false, error: 'already_running' });

  const session = await fetch('/api/auth/session').then(r => r.json()).catch(() => ({}));
  if (!session.accessToken) return JSON.stringify({ ok: false, error: 'not_authenticated' });
  const run = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '');
  const st = { running: true, run, phase: 'listing', listed: 0, done: 0, failed: [], files: [], accounts: [],
               started: Date.now(), retries: 0 };
  st.progress = () => ({ running: st.running, phase: st.phase, listed: st.listed, done: st.done,
                         failed: st.failed.length, files: st.files.length, retries: st.retries,
                         minutes: Math.round((Date.now() - st.started) / 6000) / 10, error: st.error });
  window.__cgx = st;

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let token = session.accessToken;
  async function api(path, acct, tries = 12) {
    for (let i = 0; i < tries; i++) {
      const r = await fetch(path, { headers: { Authorization: 'Bearer ' + token,
                                               ...(acct ? { 'ChatGPT-Account-Id': acct } : {}) } });
      if (r.ok) return r.json();
      if (r.status === 404) return null;
      if (r.status === 401) {  // the session token expires during a multi-hour run: refresh and retry
        const s2 = await fetch('/api/auth/session').then(x => x.json()).catch(() => ({}));
        if (s2.accessToken) token = s2.accessToken;
        st.retries++; continue;
      }
      if (r.status === 429) {  // honour Retry-After; the history-detail limiter goes from 4 s to 60 s when pushed
        st.retries++; const w = +(r.headers.get('retry-after') || 0);
        st.lastRetryAfter = w; await sleep(Math.max(w * 1000, 2000 * 2 ** Math.min(i, 5))); i = Math.min(i, 4); continue;
      }
      if (r.status >= 500) { st.retries++; await sleep(2000 * 2 ** i); continue; }
      throw new Error('http_' + r.status + ' ' + path);
    }
    throw new Error('gave_up ' + path);
  }
  function save(lines, n) {
    const name = `chatgpt-export-${run}-${String(n).padStart(3, '0')}.jsonl`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n') + '\n'], { type: 'application/x-ndjson' }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    st.files.push(name);
  }

  (async () => {
    try {
      const check = await api('/backend-api/accounts/check/v4-2023-04-27');
      let accts = Object.entries(check.accounts || {}).map(([k, v]) => ({
        id: v.account?.account_id || k, structure: v.account?.structure, plan: v.account?.plan_type,
        name: v.account?.name || null }));
      // accounts/check can list the same workspace twice under different keys (seen 2026-11-22): dedupe by id.
      accts = accts.filter((a, i) => accts.findIndex(b => b.id === a.id) === i);
      if (OPTS.accounts) accts = accts.filter(a => OPTS.accounts.includes(a.id));
      st.accounts = accts;

      // 1. list
      const seen = new Map();
      const add = (item, acct, source) => {
        if (!item?.id || seen.has(item.id)) return;
        if (OPTS.updatedAfter && item.update_time && new Date(item.update_time) <= new Date(OPTS.updatedAfter)) return;
        seen.set(item.id, { id: item.id, acct, source, title: item.title ?? null,
                            create_time: item.create_time ?? null, update_time: item.update_time ?? null });
        st.listed = seen.size;
      };
      const full = () => OPTS.limit && seen.size >= OPTS.limit;
      for (const a of accts) {
        for (const arch of OPTS.archived ? [false, true] : [false]) {
          // listPages pages at a time; stop after a batch containing a short page
          for (let base = 0, more = true; more && !full(); base += 100 * OPTS.listPages) {
            const pages = await Promise.all(Array.from({ length: OPTS.listPages }, (_, k) =>
              api(`/backend-api/conversations?offset=${base + 100 * k}&limit=100&order=updated&is_archived=${arch}`, a.id)));
            for (const d of pages) {
              const items = d?.items || [];
              items.forEach(it => add(it, a.id, arch ? 'archived' : 'list'));
              if (items.length < 100) more = false;
            }
            await sleep(OPTS.delayMs);
          }
        }
        if (OPTS.projects && !full()) {
          let cursor = null, projects = [];
          do {  // the sidebar endpoint lists Projects ("snorlax" gizmos)
            const d = await api(`/backend-api/gizmos/snorlax/sidebar?conversations_per_gizmo=0${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}`, a.id);
            (d?.items || []).forEach(x => { const g = x.gizmo?.gizmo || x.gizmo; if (g?.id) projects.push(g.id); });
            cursor = d?.cursor && d.cursor !== cursor && (d?.items || []).length ? d.cursor : null;
          } while (cursor);
          st.projects = projects.length;
          await Promise.all(projects.map(async g => {  // projects in parallel
            let c = '0';
            const cursors = new Set();
            while (c !== null && !full() && !cursors.has(c)) {  // guard: a repeated cursor would loop forever
              cursors.add(c);
              const d = await api(`/backend-api/gizmos/${g}/conversations?cursor=${encodeURIComponent(c)}`, a.id);
              const items = d?.items || [];
              items.forEach(it => add(it, a.id, 'project:' + g));
              c = items.length ? (d?.cursor ?? null) : null;
            }
          }));
        }
      }
      let queue = [...seen.values()];
      if (OPTS.ids) {  // priority list: only these ids, in the given order
        const pos = new Map(OPTS.ids.map((id, k) => [id, k]));
        queue = queue.filter(q => pos.has(q.id)).sort((x, y) => pos.get(x.id) - pos.get(y.id));
      }
      if (OPTS.limit) queue = queue.slice(0, OPTS.limit);
      st.listed = queue.length;

      // 2. fetch
      st.phase = 'fetching';
      let buf = [], fileNo = 0, i = 0;
      const worker = async () => {
        while (i < queue.length) {
          const item = queue[i++];
          try {
            const conv = await api('/backend-api/conversation/' + item.id, item.acct);
            if (conv && conv.mapping) {
              conv.conversation_id = conv.conversation_id || item.id;
              conv._account_id = item.acct; conv._source = item.source; conv._listed = item;
              buf.push(JSON.stringify(conv));
            } else st.failed.push({ id: item.id, error: 'empty' });
          } catch (e) { st.failed.push({ id: item.id, error: String(e.message || e) }); }
          st.done++;
          if (buf.length >= OPTS.chunk) { const out = buf; buf = []; save(out, ++fileNo); }
          if (OPTS.delayMs) await sleep(OPTS.delayMs);
        }
      };
      await Promise.all(Array.from({ length: OPTS.concurrency }, worker));
      if (buf.length) save(buf, ++fileNo);
      // manifest: what was listed, what failed (no bodies)
      save([JSON.stringify({ manifest: true, run, accounts: accts, listed: queue.map(q => ({ ...q })), failed: st.failed,
                             opts: OPTS, finished: new Date().toISOString() })], 0);
      st.phase = 'done';
    } catch (e) { st.error = String(e.message || e); st.phase = 'error'; }
    st.running = false;
  })();
  return JSON.stringify({ ok: true, started: run, opts: OPTS });
})()
