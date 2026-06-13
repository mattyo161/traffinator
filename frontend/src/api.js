async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  let body = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const message =
      body?.error ||
      (body && typeof body === 'object' ? JSON.stringify(body) : null) ||
      `Request failed (${res.status})`
    throw new Error(message)
  }
  return body
}

export const api = {
  setupStatus: () => request('/api/setup/status'),
  saveSetup: (apiKey) =>
    request('/api/setup', { method: 'POST', body: JSON.stringify({ api_key: apiKey }) }),
  geocode: (query, region) =>
    request('/api/geocode', { method: 'POST', body: JSON.stringify({ query, region }) }),
  analyze: (payload) =>
    request('/api/analyze', { method: 'POST', body: JSON.stringify(payload) }),
}
