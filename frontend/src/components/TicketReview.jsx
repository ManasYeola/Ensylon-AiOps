import React, { useState, useEffect } from 'react';
import {
  FileText,
  Lock,
  Lightbulb,
  CheckCircle,
  XCircle,
  Edit3,
  ExternalLink,
  Sparkles,
  AlertOctagon,
  Send,
  RefreshCw,
  Clock,
  Activity,
  Layers,
  Shield,
  HelpCircle,
  Settings,
} from 'lucide-react';
import { api } from '../services/api';

export default function TicketReview({
  incident,
  onTicketPublished,
  jiraTickets,
}) {
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState('');
  const [editedSummary, setEditedSummary] = useState('');
  const [editedRootCause, setEditedRootCause] = useState('');
  const [editedSteps, setEditedSteps] = useState('');
  const [draftsCache, setDraftsCache] = useState({});

  // Jira Cloud Integration Config
  const [jiraConfig, setJiraConfig] = useState(null);
  const [isJiraModalOpen, setIsJiraModalOpen] = useState(false);
  const [jiraForm, setJiraForm] = useState({
    jira_url: '',
    jira_email: '',
    jira_api_token: '',
    jira_project_key: '',
    jira_issue_type: 'Task',
  });
  const [savingJiraConfig, setSavingJiraConfig] = useState(false);

  // Fetch Jira config on mount
  useEffect(() => {
    api.getJiraConfig()
      .then((cfg) => {
        setJiraConfig(cfg);
        setJiraForm({
          jira_url: cfg.jira_url || '',
          jira_email: cfg.jira_email || '',
          jira_api_token: '',
          jira_project_key: cfg.jira_project_key || '',
          jira_issue_type: cfg.jira_issue_type || 'Task',
        });
      })
      .catch(() => {});
  }, []);

  // Auto-load or auto-generate draft for the selected incident (cached once)
  const loadDraft = async () => {
    if (!incident) return;

    // Fast-path: return client-side cached draft immediately without any network or LLM calls
    if (draftsCache[incident.id]) {
      const cached = draftsCache[incident.id];
      setDraft(cached);
      setEditedTitle(cached.title || '');
      setEditedSummary(cached.summary || '');
      setEditedRootCause(cached.suspected_root_cause || '');
      setEditedSteps((cached.investigation_steps || []).join('\n'));
      setError(null);
      setIsEditing(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setIsEditing(false);

    try {
      let currentDraft;
      try {
        currentDraft = await api.getDraft(incident.id);
      } catch {
        // If draft not yet generated, auto-synthesize it on demand (backed by backend singleton)
        currentDraft = await api.createDraft(incident.id);
      }
      setDraft(currentDraft);
      setDraftsCache((prev) => ({ ...prev, [incident.id]: currentDraft }));
      setEditedTitle(currentDraft.title || '');
      setEditedSummary(currentDraft.summary || '');
      setEditedRootCause(currentDraft.suspected_root_cause || '');
      setEditedSteps((currentDraft.investigation_steps || []).join('\n'));
    } catch (err) {
      setError(`Failed to auto-generate draft: ${err.message}`);
      setDraft(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDraft();
  }, [incident?.id]);

  // Human review action
  const handleReview = async (action) => {
    if (!incident || !draft) return;
    setReviewing(true);
    setError(null);
    try {
      let payload = null;
      if (action === 'edit') {
        payload = {
          title: editedTitle,
          summary: editedSummary,
          suspected_root_cause: editedRootCause,
          investigation_steps: editedSteps
            .split('\n')
            .map((s) => s.trim())
            .filter((s) => s.length > 0),
        };
      }
      const reviewed = await api.submitReview(incident.id, action, payload);
      setDraft(reviewed);
      setDraftsCache((prev) => ({ ...prev, [incident.id]: reviewed }));
      setIsEditing(false);
    } catch (err) {
      setError(`Review failed: ${err.message}`);
    } finally {
      setReviewing(false);
    }
  };

  // Save Jira Settings
  const handleSaveJiraConfig = async (e) => {
    e.preventDefault();
    setSavingJiraConfig(true);
    setError(null);
    try {
      const updated = await api.updateJiraConfig(jiraForm);
      setJiraConfig(updated);
      setIsJiraModalOpen(false);
    } catch (err) {
      setError(`Failed to save Jira settings: ${err.message}`);
    } finally {
      setSavingJiraConfig(false);
    }
  };

  // Publish to Jira (auto-approves unreviewed draft in 1-click for instant publishing)
  const handlePublishJira = async () => {
    if (!incident || !draft) return;
    setPublishing(true);
    setError(null);
    try {
      // Auto-approve if needed so 1-click publishing works seamlessly
      if (draft.review_status !== 'approved') {
        const approvedDraft = await api.submitReview(incident.id, 'approve');
        setDraft(approvedDraft);
      }
      const ticket = await api.publishToJira(incident.id);
      if (onTicketPublished) {
        onTicketPublished(ticket);
      }
    } catch (err) {
      setError(`Jira publishing failed: ${err.message}`);
    } finally {
      setPublishing(false);
    }
  };

  if (!incident) {
    return (
      <div
        className="glass-card"
        style={{
          padding: '30px',
          textAlign: 'center',
          color: 'var(--text-secondary)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        Select an incident to view or draft a ticket for human review.
      </div>
    );
  }

  // Find if this incident is already published to Jira
  const publishedTicket = (jiraTickets || []).find(
    (t) => t.incident_id === incident.id
  );
  const isApproved = draft?.review_status === 'approved' || !!publishedTicket;

  const severityScore =
    draft?.severity !== undefined ? draft.severity : incident.severity;
  const confidenceScore =
    draft?.confidence !== undefined ? draft.confidence : incident.confidence;
  const affectedServices =
    draft?.affected_services || incident.services || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Error banner */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(244, 63, 94, 0.12)',
            border: '1px solid rgba(244, 63, 94, 0.3)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--rose)',
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <AlertOctagon size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state: auto-synthesizing draft */}
      {!draft && loading && (
        <div
          className="glass-card"
          style={{ padding: '50px 30px', textAlign: 'center', borderRadius: 'var(--radius-xl)' }}
        >
          <RefreshCw
            size={36}
            color="var(--purple)"
            className="animate-spin"
            style={{ margin: '0 auto 16px' }}
          />
          <h3 style={{ fontSize: '1.15rem', marginBottom: '8px' }}>
            Auto-Synthesizing Incident Ticket with Claude...
          </h3>
          <p
            style={{
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              maxWidth: '500px',
              margin: '0 auto',
              lineHeight: 1.5,
            }}
          >
            Claude is analyzing the{' '}
            <strong>{incident.signal_ids?.length || 0}</strong> correlated
            telemetry signals and topological causal chains to produce the
            structured incident draft for your review.
          </p>
        </div>
      )}

      {/* Error state if auto-generation failed */}
      {!draft && !loading && (
        <div
          className="glass-card"
          style={{ padding: '40px 30px', textAlign: 'center', borderRadius: 'var(--radius-xl)' }}
        >
          <AlertOctagon
            size={36}
            color="var(--rose)"
            style={{ margin: '0 auto 12px' }}
          />
          <h3 style={{ fontSize: '1.1rem', marginBottom: '8px' }}>
            Draft Synthesis Failed
          </h3>
          <p
            style={{
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              maxWidth: '480px',
              margin: '0 auto 20px',
            }}
          >
            {error || 'Unable to retrieve or generate incident ticket draft.'}
          </p>
          <button
            className="btn btn-secondary"
            onClick={loadDraft}
            style={{ padding: '8px 20px', fontSize: '0.85rem' }}
          >
            <RefreshCw size={14} />
            <span>Retry Auto-Synthesis</span>
          </button>
        </div>
      )}

      {/* Render draft once generated */}
      {draft && (
        <div className="glass-card" style={{ padding: '24px', borderRadius: 'var(--radius-xl)' }}>
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid var(--border-subtle)',
              paddingBottom: '16px',
              marginBottom: '16px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  marginBottom: '4px',
                }}
              >
                <FileText size={18} color="#D6A62C" />
                <span
                  className="font-mono"
                  style={{
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    fontSize: '0.95rem',
                  }}
                >
                  Draft for {incident.id}
                </span>
                <span
                  className={`badge ${
                    draft.review_status === 'approved'
                      ? 'badge-green'
                      : draft.review_status === 'rejected'
                      ? 'badge-rose'
                      : 'badge-amber'
                  }`}
                  style={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}
                >
                  Status: {draft.review_status || 'DRAFT'}
                </span>
                {draft.edited_by && (
                  <span
                    style={{
                      fontSize: '0.72rem',
                      color: 'var(--text-secondary)',
                      background: 'rgba(61, 70, 84, 0.08)',
                      padding: '3px 10px',
                      borderRadius: 'var(--radius-full)',
                    }}
                  >
                    Reviewer: {draft.edited_by}
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Fingerprint:{' '}
                <span className="font-mono">
                  {incident.fingerprint_id?.substring(0, 16) || 'None'}
                </span>
              </p>
            </div>

            {/* Jira Publish status & controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {/* Configure Jira Modal Trigger */}
              <button
                className="btn btn-secondary"
                onClick={() => setIsJiraModalOpen(true)}
                title="Configure Live Atlassian Jira Cloud connection"
                style={{
                  padding: '6px 12px',
                  fontSize: '0.75rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: jiraConfig?.is_configured ? 'rgba(16, 185, 129, 0.12)' : '#EAE6DB',
                  border: jiraConfig?.is_configured ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid var(--border-subtle)',
                }}
              >
                <Settings size={14} color={jiraConfig?.is_configured ? 'var(--green)' : 'var(--text-muted)'} />
                <span style={{ color: jiraConfig?.is_configured ? 'var(--green)' : 'var(--text-secondary)' }}>
                  {jiraConfig?.is_configured ? `Jira: ${jiraConfig.jira_project_key || 'Connected'}` : 'Configure Jira'}
                </span>
              </button>

              {publishedTicket ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 14px',
                    background: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    borderRadius: 'var(--radius-lg)',
                  }}
                >
                  <CheckCircle size={18} color="var(--green)" />
                  <div>
                    <div
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        color: 'var(--green)',
                      }}
                    >
                      Published: {publishedTicket.id}
                    </div>
                    <div
                      style={{
                        fontSize: '0.7rem',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {publishedTicket.url ? 'Live Atlassian Jira Cloud Issue' : `Persisted to output/tickets/${publishedTicket.id}.json`}
                    </div>
                  </div>

                  {publishedTicket.url && (
                    <a
                      href={publishedTicket.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-primary"
                      style={{
                        padding: '5px 12px',
                        fontSize: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        textDecoration: 'none',
                        marginLeft: '4px',
                      }}
                    >
                      <span>Open in Jira</span>
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              ) : (
                <button
                  className="btn btn-primary"
                  onClick={handlePublishJira}
                  disabled={publishing}
                  title="Automatically approve and publish ticket directly to Jira in one click"
                  style={{
                    padding: '8px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontWeight: 600,
                  }}
                >
                  {publishing ? (
                    <>
                      <RefreshCw size={15} className="animate-spin" />
                      <span>Publishing to Jira...</span>
                    </>
                  ) : (
                    <>
                      <Send size={15} />
                      <span>Publish to Jira</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Structured Metadata Bar: Severity, Confidence, Affected Services */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '16px',
              padding: '12px 18px',
              background: '#EAE6DB',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              marginBottom: '20px',
              fontSize: '0.8rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Severity:</span>
              <span
                style={{
                  fontWeight: 700,
                  color:
                    severityScore >= 80
                      ? 'var(--rose)'
                      : severityScore >= 50
                      ? 'var(--amber)'
                      : 'var(--green)',
                }}
              >
                {typeof severityScore === 'number'
                  ? severityScore.toFixed(1)
                  : severityScore}
                /100
              </span>
            </div>

            <div
              style={{
                width: '1px',
                height: '14px',
                background: 'var(--border-subtle)',
              }}
            />

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Confidence:</span>
              <span
                className="font-mono"
                style={{ fontWeight: 700, color: '#D6A62C' }}
              >
                {(confidenceScore * 100).toFixed(0)}%
              </span>
            </div>

            <div
              style={{
                width: '1px',
                height: '14px',
                background: 'var(--border-subtle)',
              }}
            />

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>
                Affected Services:
              </span>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {affectedServices.map((svc, i) => (
                  <span
                    key={i}
                    className="font-mono badge badge-purple"
                    style={{
                      fontSize: '0.72rem',
                    }}
                  >
                    {svc}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Ticket Title & Summary */}
          <div style={{ marginBottom: '22px' }}>
            {isEditing ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
              >
                <div>
                  <label
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-secondary)',
                      fontWeight: 600,
                      display: 'block',
                      marginBottom: '4px',
                    }}
                  >
                    Ticket Title:
                  </label>
                  <input
                    type="text"
                    value={editedTitle}
                    onChange={(e) => setEditedTitle(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 14px',
                      background: '#FFFFFF',
                      border: '1px solid rgba(61, 70, 84, 0.2)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-sans)',
                      fontSize: '0.9rem',
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-secondary)',
                      fontWeight: 600,
                      display: 'block',
                      marginBottom: '4px',
                    }}
                  >
                    Ticket Summary:
                  </label>
                  <textarea
                    rows={3}
                    value={editedSummary}
                    onChange={(e) => setEditedSummary(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      background: '#FFFFFF',
                      border: '1px solid rgba(61, 70, 84, 0.2)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-sans)',
                      fontSize: '0.88rem',
                    }}
                  />
                </div>
              </div>
            ) : (
              <div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 700,
                    marginBottom: '8px',
                    color: 'var(--text-primary)',
                  }}
                >
                  {draft.title}
                </h3>
                <p
                  style={{
                    fontSize: '0.88rem',
                    color: 'var(--text-secondary)',
                    lineHeight: 1.6,
                  }}
                >
                  {draft.summary}
                </p>
              </div>
            )}
          </div>

          {/* Source-labeled Signal Timeline */}
          {draft.timeline && draft.timeline.length > 0 && (
            <div
              style={{
                background: '#F2EFE5',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-lg)',
                padding: '16px',
                marginBottom: '20px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '10px',
                }}
              >
                <Clock size={16} color="#D6A62C" />
                <h4
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  Signal Timeline (Source-Labeled)
                </h4>
              </div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  maxHeight: '160px',
                  overflowY: 'auto',
                }}
              >
                {draft.timeline.map((entry, idx) => (
                  <div
                    key={idx}
                    className="font-mono"
                    style={{
                      fontSize: '0.78rem',
                      padding: '8px 12px',
                      background: '#FAF8F0',
                      borderLeft: '3px solid #D6A62C',
                      borderRadius: '0 var(--radius-md) var(--radius-md) 0',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {entry}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Observed Evidence vs Suspected Root Cause */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '18px',
              marginBottom: '24px',
            }}
          >
            {/* 1. Observed Evidence (Deterministic facts, strictly telemetry) */}
            <div
              style={{
                background: 'rgba(214, 166, 44, 0.06)',
                border: '1px solid rgba(214, 166, 44, 0.25)',
                borderRadius: 'var(--radius-lg)',
                padding: '18px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '8px',
                }}
              >
                <Lock size={16} color="#D6A62C" />
                <h4
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    color: '#785A00',
                  }}
                >
                  Observed Evidence (Facts)
                </h4>
              </div>
              <p
                style={{
                  fontSize: '0.72rem',
                  color: 'var(--text-muted)',
                  marginBottom: '10px',
                }}
              >
                Deterministic evidence package from telemetry signals (never
                invented by LLM).
              </p>
              <ul
                style={{
                  listStyleType: 'disc',
                  paddingLeft: '18px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  fontSize: '0.78rem',
                  color: 'var(--text-primary)',
                  maxHeight: '220px',
                  overflowY: 'auto',
                }}
              >
                {(draft.observed_evidence || []).map((ev, i) => (
                  <li key={i} style={{ lineHeight: 1.4 }}>
                    {ev}
                  </li>
                ))}
              </ul>
            </div>

            {/* 2. Suspected Root Cause (Unverified LLM Hypothesis) */}
            <div
              style={{
                background: 'rgba(61, 70, 84, 0.05)',
                border: '1px solid rgba(61, 70, 84, 0.18)',
                borderRadius: 'var(--radius-lg)',
                padding: '18px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '8px',
                }}
              >
                <Lightbulb size={16} color="#3D4654" />
                <h4
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    color: '#3D4654',
                  }}
                >
                  Suspected Root Cause (Hypothesis)
                </h4>
              </div>
              <div
                style={{
                  padding: '6px 12px',
                  background: 'rgba(214, 166, 44, 0.15)',
                  border: '1px solid rgba(214, 166, 44, 0.35)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.72rem',
                  color: '#785A00',
                  fontWeight: 600,
                  marginBottom: '10px',
                }}
              >
                UNVERIFIED HYPOTHESIS &mdash; Requires SRE Verification
              </div>
              {isEditing ? (
                <textarea
                  rows={4}
                  value={editedRootCause}
                  onChange={(e) => setEditedRootCause(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: '#FFFFFF',
                    border: '1px solid rgba(61, 70, 84, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.82rem',
                  }}
                />
              ) : (
                <p
                  style={{
                    fontSize: '0.82rem',
                    color: 'var(--text-primary)',
                    lineHeight: 1.5,
                  }}
                >
                  {draft.suspected_root_cause}
                </p>
              )}
            </div>
          </div>

          {/* Suggested Investigation Steps */}
          <div
            style={{
              background: '#F2EFE5',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              padding: '18px',
              marginBottom: '24px',
            }}
          >
            <h4
              style={{
                fontSize: '0.88rem',
                fontWeight: 600,
                marginBottom: '10px',
                color: 'var(--text-primary)',
              }}
            >
              Suggested Investigation Steps
            </h4>
            {isEditing ? (
              <div>
                <p
                  style={{
                    fontSize: '0.72rem',
                    color: 'var(--text-muted)',
                    marginBottom: '6px',
                  }}
                >
                  Enter each step on a new line:
                </p>
                <textarea
                  rows={4}
                  value={editedSteps}
                  onChange={(e) => setEditedSteps(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: '#FFFFFF',
                    border: '1px solid rgba(61, 70, 84, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.82rem',
                  }}
                />
              </div>
            ) : (
              <ol
                style={{
                  paddingLeft: '20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)',
                }}
              >
                {(draft.investigation_steps || []).map((step, i) => (
                  <li key={i} style={{ lineHeight: 1.4 }}>
                    {step}
                  </li>
                ))}
              </ol>
            )}
          </div>

          {/* Human Review Gate Actions */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderTop: '1px solid var(--border-subtle)',
              paddingTop: '16px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Human Gate: Review, edit, approve or reject before Jira publication.
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {isEditing ? (
                <>
                  <button
                    className="btn btn-secondary"
                    onClick={() => setIsEditing(false)}
                    disabled={reviewing}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-success"
                    onClick={() => handleReview('edit')}
                    disabled={reviewing}
                  >
                    Save &amp; Approve
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleReview('reject')}
                    disabled={reviewing || draft.review_status === 'rejected'}
                  >
                    <XCircle size={15} />
                    <span>Reject</span>
                  </button>

                  <button
                    className="btn btn-secondary"
                    onClick={() => setIsEditing(true)}
                    disabled={reviewing}
                  >
                    <Edit3 size={15} />
                    <span>Edit Draft</span>
                  </button>

                  <button
                    className="btn btn-success"
                    onClick={() => handleReview('approve')}
                    disabled={reviewing || draft.review_status === 'approved'}
                  >
                    <CheckCircle size={15} />
                    <span>Approve Draft</span>
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Jira Cloud Settings Modal */}
      {isJiraModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(37, 37, 37, 0.45)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 3000,
            padding: '20px',
          }}
        >
          <div
            className="glass-card"
            style={{
              width: '100%',
              maxWidth: '520px',
              padding: '24px',
              borderRadius: 'var(--radius-xl)',
              boxShadow: 'var(--shadow-xl)',
              background: '#FAF8F0',
              border: '1px solid rgba(61, 70, 84, 0.18)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '16px',
                paddingBottom: '12px',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Settings size={20} color="#D6A62C" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Atlassian Jira Cloud Settings
                </h3>
              </div>
              <button
                onClick={() => setIsJiraModalOpen(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '1.2rem',
                }}
              >
                &times;
              </button>
            </div>

            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '16px', lineHeight: 1.5 }}>
              Connect your company's Atlassian Jira Cloud account. When you click <strong>Publish to Jira</strong>, tickets will be automatically created on your live board.
            </p>

            <form onSubmit={handleSaveJiraConfig} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Jira Cloud URL
                </label>
                <input
                  type="url"
                  placeholder="https://your-company.atlassian.net"
                  value={jiraForm.jira_url}
                  onChange={(e) => setJiraForm({ ...jiraForm, jira_url: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '0.82rem',
                    background: '#FFFFFF',
                    border: '1px solid rgba(61, 70, 84, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Atlassian Email
                </label>
                <input
                  type="email"
                  placeholder="engineer@your-company.com"
                  value={jiraForm.jira_email}
                  onChange={(e) => setJiraForm({ ...jiraForm, jira_email: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '0.82rem',
                    background: '#FFFFFF',
                    border: '1px solid rgba(61, 70, 84, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Atlassian API Token
                  </label>
                  <a
                    href="https://id.atlassian.com/manage-profile/security/api-tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '0.7rem', color: '#D6A62C', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Generate Token &rarr;
                  </a>
                </div>
                <input
                  type="password"
                  placeholder={jiraConfig?.has_token ? '•••••••••••••••• (Leave blank to keep existing)' : 'Paste Atlassian API Token'}
                  value={jiraForm.jira_api_token}
                  onChange={(e) => setJiraForm({ ...jiraForm, jira_api_token: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '0.82rem',
                    background: '#FFFFFF',
                    border: '1px solid rgba(61, 70, 84, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    Project Key
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. KAN, OPS, INC"
                    value={jiraForm.jira_project_key}
                    onChange={(e) => setJiraForm({ ...jiraForm, jira_project_key: e.target.value.toUpperCase() })}
                    required
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.82rem',
                      background: '#FFFFFF',
                      border: '1px solid rgba(61, 70, 84, 0.2)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--text-primary)',
                      textTransform: 'uppercase',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    Issue Type
                  </label>
                  <input
                    type="text"
                    placeholder="Bug, Task, Incident"
                    value={jiraForm.jira_issue_type}
                    onChange={(e) => setJiraForm({ ...jiraForm, jira_issue_type: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.82rem',
                      background: '#FFFFFF',
                      border: '1px solid rgba(61, 70, 84, 0.2)',
                      borderRadius: 'var(--radius-md)',
                      color: 'var(--text-primary)',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '14px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsJiraModalOpen(false)}
                  style={{ padding: '8px 16px', fontSize: '0.82rem' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={savingJiraConfig}
                  style={{ padding: '8px 18px', fontSize: '0.82rem' }}
                >
                  {savingJiraConfig ? 'Connecting...' : 'Save & Connect'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
