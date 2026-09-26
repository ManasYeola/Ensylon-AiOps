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

  // Fetch or auto-load draft for the selected incident
  useEffect(() => {
    if (!incident) return;
    setError(null);
    setIsEditing(false);

    const loadDraft = async () => {
      try {
        const existing = await api.getDraft(incident.id);
        setDraft(existing);
        setEditedTitle(existing.title || '');
        setEditedSummary(existing.summary || '');
        setEditedRootCause(existing.suspected_root_cause || '');
        setEditedSteps((existing.investigation_steps || []).join('\n'));
      } catch (e) {
        // No draft exists yet, set to null
        setDraft(null);
      }
    };

    loadDraft();
  }, [incident]);

  // Generate draft via Claude / LLM
  const handleGenerateDraft = async () => {
    if (!incident) return;
    setLoading(true);
    setError(null);
    try {
      const newDraft = await api.createDraft(incident.id);
      setDraft(newDraft);
      setEditedTitle(newDraft.title || '');
      setEditedSummary(newDraft.summary || '');
      setEditedRootCause(newDraft.suspected_root_cause || '');
      setEditedSteps((newDraft.investigation_steps || []).join('\n'));
    } catch (err) {
      setError(`Failed to generate draft: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

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
      setIsEditing(false);
    } catch (err) {
      setError(`Review failed: ${err.message}`);
    } finally {
      setReviewing(false);
    }
  };

  // Publish to Jira (only after explicit approval)
  const handlePublishJira = async () => {
    if (!incident || !draft) return;
    setPublishing(true);
    setError(null);
    try {
      const ticket = await api.publishToJira(incident.id);
      if (onTicketPublished) {
        onTicketPublished(ticket);
      }
    } catch (err) {
      setError(`Jira publishing blocked: ${err.message}`);
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

      {/* Draft generator banner if not generated yet */}
      {!draft ? (
        <div
          className="glass-card"
          style={{ padding: '40px', textAlign: 'center' }}
        >
          <Sparkles
            size={36}
            color="var(--purple)"
            style={{ margin: '0 auto 12px' }}
          />
          <h3 style={{ fontSize: '1.15rem', marginBottom: '8px' }}>
            Generate Incident Ticket Draft with Claude
          </h3>
          <p
            style={{
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              maxWidth: '520px',
              margin: '0 auto 20px',
              lineHeight: 1.5,
            }}
          >
            Claude analyzes the{' '}
            <strong>{incident.signal_ids?.length || 0}</strong> correlated
            telemetry signals and topological causal chains to produce a
            structured, evidence-grounded draft with strict separation of facts
            and unverified hypotheses.
          </p>
          <button
            className="btn btn-primary"
            onClick={handleGenerateDraft}
            disabled={loading}
            style={{ padding: '10px 24px', fontSize: '0.9rem' }}
          >
            {loading ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                <span>Synthesizing with Claude...</span>
              </>
            ) : (
              <>
                <Sparkles size={16} />
                <span>Generate Ticket Draft with Claude</span>
              </>
            )}
          </button>
        </div>
      ) : (
        <div className="glass-card" style={{ padding: '24px' }}>
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
                <FileText size={18} color="var(--cyan)" />
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
                      color: 'var(--text-muted)',
                      background: 'rgba(255,255,255,0.05)',
                      padding: '2px 8px',
                      borderRadius: '4px',
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

            {/* Jira Publish status */}
            {publishedTicket ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 14px',
                  background: 'rgba(16, 185, 129, 0.12)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  borderRadius: 'var(--radius-md)',
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
                    Published to Jira: {publishedTicket.id}
                  </div>
                  <div
                    style={{
                      fontSize: '0.7rem',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    Persisted to output/tickets/{publishedTicket.id}.json
                  </div>
                </div>
              </div>
            ) : (
              <button
                className="btn btn-success"
                onClick={handlePublishJira}
                disabled={publishing || !isApproved}
                title={
                  !isApproved
                    ? 'You must Approve the draft before publishing to Jira'
                    : 'Publish to Mock Jira & output/tickets/'
                }
              >
                {publishing ? (
                  <>
                    <RefreshCw size={15} className="animate-spin" />
                    <span>Publishing...</span>
                  </>
                ) : (
                  <>
                    <Send size={15} />
                    <span>Publish to Jira (PRD §22)</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Structured Metadata Bar: Severity, Confidence, Affected Services */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '16px',
              padding: '10px 14px',
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
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
                style={{ fontWeight: 600, color: 'var(--cyan)' }}
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
                    className="font-mono"
                    style={{
                      fontSize: '0.72rem',
                      padding: '2px 8px',
                      background: 'rgba(139, 92, 246, 0.15)',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      borderRadius: 'var(--radius-sm)',
                      color: '#C4B5FD',
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
                      padding: '8px 12px',
                      background: 'var(--bg-glass-input)',
                      border: '1px solid var(--border-medium)',
                      borderRadius: 'var(--radius-sm)',
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
                      padding: '8px 12px',
                      background: 'var(--bg-glass-input)',
                      border: '1px solid var(--border-medium)',
                      borderRadius: 'var(--radius-sm)',
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

          {/* Source-labeled Signal Timeline (Challenge Spec Requirement) */}
          {draft.timeline && draft.timeline.length > 0 && (
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.4)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
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
                <Clock size={16} color="var(--cyan)" />
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
                      padding: '6px 10px',
                      background: 'rgba(255, 255, 255, 0.02)',
                      borderLeft: '2px solid var(--cyan)',
                      borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {entry}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PRD Strict Separation Columns: Observed Evidence vs Suspected Root Cause */}
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
                background: 'rgba(6, 182, 212, 0.04)',
                border: '1px solid rgba(6, 182, 212, 0.2)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
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
                <Lock size={16} color="var(--cyan)" />
                <h4
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 600,
                    color: 'var(--cyan)',
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
                  color: 'var(--text-secondary)',
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
                background: 'rgba(139, 92, 246, 0.04)',
                border: '1px solid rgba(139, 92, 246, 0.2)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
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
                <Lightbulb size={16} color="var(--purple)" />
                <h4
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 600,
                    color: '#C4B5FD',
                  }}
                >
                  Suspected Root Cause (Hypothesis)
                </h4>
              </div>
              <div
                style={{
                  padding: '6px 10px',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.72rem',
                  color: 'var(--amber)',
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
                    background: 'var(--bg-glass-input)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-sm)',
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

          {/* Remediation / Suggested Investigation Steps */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '16px',
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
                    background: 'var(--bg-glass-input)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-sm)',
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

          {/* Human Review Gate Actions (PRD §21) */}
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
              Human Gate (PRD §21): Review, edit, approve or reject before Jira
              publication.
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
    </div>
  );
}
