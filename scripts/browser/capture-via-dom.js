// FALLBACK ONLY. Scrape the rendered conversation out of the DOM.
//
// Use this when capture-via-api.js fails — typically because the account uses
// an SSO flow that does not expose /api/auth/session, or OpenAI has changed the
// backend route. It is strictly worse than the API path and you should say so
// when you use it.
//
// The list is virtualised: on a 34-message thread only about 5 messages exist
// in the DOM at any scroll position, and data-testid indices start wherever you
// happen to be (conversation-turn-6, not -1). So this scrolls the container to
// the top and walks down, accumulating by data-message-id.
//
// Known losses versus the API route: no create_time per message, no model slug
// beyond what is on the node, no alternate branches, no tool/hidden messages,
// and canvas documents appear only as their rendered preview.
//
// IMPORTANT — the leading `await` is required, not stylistic. javascript_tool
// returns the value of the last expression without awaiting it, so a bare
// `(async () => {...})()` serializes as `{}` and the capture looks like it
// silently returned nothing. Verified 2026-08-24.

await (async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const scroller = (() => {
    const nodes = [...document.querySelectorAll('div, main')];
    return nodes.filter(el => el.scrollHeight > el.clientHeight + 200)
                .sort((a, b) => b.scrollHeight - a.scrollHeight)[0]
           || document.scrollingElement;
  })();

  const collected = new Map();
  const harvest = () => {
    for (const el of document.querySelectorAll('[data-message-author-role]')) {
      const id = el.getAttribute('data-message-id');
      if (!id || collected.has(id)) continue;
      collected.set(id, {
        message_id: id,
        role: el.getAttribute('data-message-author-role'),
        model: el.getAttribute('data-message-model-slug') || null,
        text: (el.innerText || '').trim(),
        dom_order: collected.size,
      });
    }
  };

  scroller.scrollTop = 0;
  await sleep(700);
  harvest();

  let lastCount = -1, stalls = 0;
  const step = Math.max(300, Math.floor(scroller.clientHeight * 0.7));
  for (let i = 0; i < 400 && stalls < 4; i++) {
    scroller.scrollTop += step;
    await sleep(220);
    harvest();
    if (collected.size === lastCount) stalls++; else stalls = 0;
    lastCount = collected.size;
    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5) {
      await sleep(400);
      harvest();
      break;
    }
  }

  const turns = [...collected.values()];
  const id = location.pathname.split(/\/(?:c|share)\//)[1]?.split(/[?#]/)[0] || 'unknown';

  // Emitted in the normalizer's own shape so the same renderers apply. Fields
  // the DOM cannot supply are null rather than invented.
  const doc = {
    schema_version: '1',
    source: { kind: 'dom_scrape', conversation_id: id, url: location.href,
              captured_at: new Date().toISOString() },
    conversation: {
      title: document.title.replace(/\s*[-|]\s*ChatGPT\s*$/, ''),
      created_at: null, updated_at: null, date_held: null,
      default_model: turns.find(t => t.model)?.model || null,
      models_used: [...new Set(turns.map(t => t.model).filter(Boolean))],
    },
    stats: {
      total_turns: turns.length,
      user_messages: turns.filter(t => t.role === 'user').length,
      assistant_messages: turns.filter(t => t.role === 'assistant').length,
      other_messages: turns.filter(t => !['user', 'assistant'].includes(t.role)).length,
      user_chars: turns.filter(t => t.role === 'user')
                       .reduce((n, t) => n + t.text.length, 0),
      assistant_chars: turns.filter(t => t.role === 'assistant')
                            .reduce((n, t) => n + t.text.length, 0),
      artifacts: 0, citations: 0,
      first_message_at: null, last_message_at: null, duration_minutes: null,
      nodes_in_mapping: null, nodes_on_rendered_branch: turns.length,
      branch_points: null, has_alternate_branches: null,
      skipped: { hidden: null, tool: null, empty: 0, system: null },
      capture_is_lossy: true,
    },
    turns: turns.map((t, i) => ({
      index: i + 1, role: t.role, author_name: null, message_id: t.message_id,
      created_at: null, model: t.role === 'assistant' ? t.model : null,
      channel: null, recipient: null, content_type: 'text',
      hidden: false, excluded_from_context: false,
      text: t.text, artifacts: [], citations: [],
    })),
    artifacts: [],
    unhandled: [{ where: 'capture', note: 'DOM scrape: timestamps, branches, ' +
                  'tool messages and artifact payloads are unavailable' }],
  };

  const blob = new Blob([JSON.stringify(doc)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'chatgpt-normalized-' + id + '.json';
  document.body.appendChild(a); a.click(); a.remove();

  return JSON.stringify({
    ok: turns.length > 0,
    filename: a.download,
    already_normalized: true,
    turns: turns.length,
    user_messages: doc.stats.user_messages,
    assistant_messages: doc.stats.assistant_messages,
    warning: 'lossy capture — prefer capture-via-api.js',
  });
})()
