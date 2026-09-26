/**
 * API client for Ensylon AIOps FastAPI backend
 */

const BASE_URL = ''; // Uses Vite proxy in dev, or same host in prod

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const config = {
    ...options,
    headers,
  };

  try {
    const res = await fetch(url, config);
    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}`;
      try {
        const errorJson = await res.json();
        errorDetail = errorJson.detail || errorDetail;
      } catch (e) {
        // ignore json parse error
      }
      throw new Error(errorDetail);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  // Health & Config
  getHealth: () => request('/api/health'),
  getConfig: () => request('/api/config'),

  // Signals
  getSignals: () => request('/api/signals'),
  getSignal: (id) => request(`/api/signals/${id}`),

  // Incidents
  getIncidents: () => request('/api/incidents'),
  getIncident: (id) => request(`/api/incidents/${id}`),
  getEvidenceGraph: (id) => request(`/api/incidents/${id}/graph`),
  getFingerprint: (id) => request(`/api/incidents/${id}/fingerprint`),

  // Drafts & LLM
  createDraft: (incidentId) =>
    request(`/api/incidents/${incidentId}/draft`, { method: 'POST' }),
  getDraft: (incidentId) => request(`/api/incidents/${incidentId}/draft`),

  // Human Review Gate
  submitReview: (incidentId, action, editedDraft = null) =>
    request(`/api/incidents/${incidentId}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, edited_draft: editedDraft }),
    }),

  // Jira
  publishToJira: (incidentId) =>
    request(`/api/jira/tickets?incident_id=${encodeURIComponent(incidentId)}`, {
      method: 'POST',
    }),
  getJiraTickets: () => request('/api/jira/tickets'),

  // Demo Pipeline & Webhooks
  getStreamsStatus: () => request('/api/streams/status'),
  testWebhook: (payload) =>
    request('/webhooks/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
