// Capture the open ChatGPT conversation as raw JSON, saved to the browser's
// download directory. Paste into mcp__claude-in-chrome__javascript_tool while a
// chatgpt.com conversation tab is focused.
//
// Why a download rather than a return value: the tool result is transcribed
// into the agent's context. A long thread would both blow the context budget
// and copy a private conversation into a chat log. The file goes to disk, and
// only the summary comes back.
//
// Works for /c/<id> (own conversation, needs the session token) and
// /share/<id> (public link, no token). Returns a one-line JSON summary.
//
// IMPORTANT — the leading `await` is required, not stylistic. javascript_tool
// returns the value of the last expression without awaiting it, so a bare
// `(async () => {...})()` serializes as `{}` and the capture looks like it
// silently returned nothing. Verified 2026-08-24.

await (async () => {
  const path = location.pathname;
  const isShare = path.includes('/share/');
  const id = path.split(isShare ? '/share/' : '/c/')[1]?.split(/[?#]/)[0];
  if (!id) {
    return JSON.stringify({ ok: false, error: 'not_on_a_conversation_page', path });
  }

  let headers = {};
  if (!isShare) {
    const session = await fetch('/api/auth/session').then(r => r.json()).catch(() => ({}));
    if (!session.accessToken) {
      return JSON.stringify({ ok: false, error: 'not_authenticated',
                              hint: 'log in to chatgpt.com in this browser profile' });
    }
    headers = { Authorization: 'Bearer ' + session.accessToken };
  }

  const endpoint = isShare
    ? '/backend-api/share/' + id
    : '/backend-api/conversation/' + id;

  const res = await fetch(endpoint, { headers });
  if (!res.ok) {
    return JSON.stringify({ ok: false, error: 'http_' + res.status, endpoint });
  }
  const data = await res.json();

  // A share payload nests the thread one level down.
  const conv = data.mapping ? data : (data.conversation || data);
  if (!conv.mapping) {
    return JSON.stringify({ ok: false, error: 'no_mapping_in_payload',
                            keys: Object.keys(data) });
  }
  conv.conversation_id = conv.conversation_id || id;

  const blob = new Blob([JSON.stringify(conv)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'chatgpt-conversation-' + id + '.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);

  const roles = {};
  let leaves = 0, branchPoints = 0;
  for (const node of Object.values(conv.mapping)) {
    if (!node.children || node.children.length === 0) leaves++;
    if (node.children && node.children.length > 1) branchPoints++;
    const r = node.message?.author?.role;
    if (r) roles[r] = (roles[r] || 0) + 1;
  }

  return JSON.stringify({
    ok: true,
    filename: a.download,
    conversation_id: id,
    source_kind: isShare ? 'shared_link' : 'backend_api',
    bytes: blob.size,
    nodes: Object.keys(conv.mapping).length,
    roles,
    branch_points: branchPoints,
    leaves,
    // Titles can be sensitive; length only, so the agent can confirm a hit
    // without the title entering the transcript.
    title_length: (conv.title || '').length,
  });
})()
