const TOKEN_KEY = 'authToken'

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  set token(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  },
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (auth.token) headers.Authorization = `Token ${auth.token}`
  const res = await fetch(path, { ...options, headers })
  let body = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON or empty body */
  }
  if (!res.ok) {
    const message =
      body?.error ||
      (body && typeof body === 'object' ? JSON.stringify(body) : null) ||
      `Request failed (${res.status})`
    const err = new Error(message)
    err.status = res.status
    throw err
  }
  return body
}

export const api = {
  config: () => request('/api/config'),
  saveSetup: (apiKey) =>
    request('/api/setup', { method: 'POST', body: JSON.stringify({ api_key: apiKey }) }),
  geocode: (query, region) =>
    request('/api/geocode', { method: 'POST', body: JSON.stringify({ query, region }) }),
  route: (origin, destination) =>
    request('/api/route', { method: 'POST', body: JSON.stringify({ origin, destination }) }),
  analyze: (payload) =>
    request('/api/analyze', { method: 'POST', body: JSON.stringify(payload) }),

  // Auth
  googleLogin: (credential) =>
    request('/api/auth/google', { method: 'POST', body: JSON.stringify({ credential }) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),

  // Saved data
  listAddresses: () => request('/api/saved-addresses/'),
  createAddress: (data) =>
    request('/api/saved-addresses/', { method: 'POST', body: JSON.stringify(data) }),
  deleteAddress: (id) =>
    request(`/api/saved-addresses/${id}/`, { method: 'DELETE' }),
  listRoutes: () => request('/api/saved-routes/'),
  createRoute: (data) =>
    request('/api/saved-routes/', { method: 'POST', body: JSON.stringify(data) }),
  deleteRoute: (id) =>
    request(`/api/saved-routes/${id}/`, { method: 'DELETE' }),
}
