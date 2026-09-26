import React from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  FileText,
  HardDrive,
  Layers,
  Radio,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  XCircle,
} from 'lucide-react';
import { formatIST } from '../utils/time';

export default function IncidentDetails({ incident, allSignals = [], onNavigate }) {
  if (!incident) {
    return (
      <div className="glass-card" style={{ padding: '40px', textAlign: 'center', color: '#565F6E', background: '#FAF8F0' }}>
        <ShieldCheck size={36} color="#D6A62C" style={{ margin: '0 auto 12px' }} />
        <h3 style={{ fontSize: '1.1rem', marginBottom: '6px', color: '#252525' }}>
          No Incident Selected
        </h3>
        <p style={{ fontSize: '0.85rem', color: '#565F6E', maxWidth: '440px', margin: '0 auto 16px' }}>
          Select an incident from the dashboard to inspect deterministic validation gates, severity breakdowns, and correlated telemetry signals.
        </p>
        <button
          className="btn btn-secondary"
          onClick={() => onNavigate && onNavigate('dashboard')}
          style={{ borderRadius: 'var(--radius-full)' }}
        >
          <ArrowLeft size={16} />
          <span>Back to Dashboard</span>
        </button>
      </div>
    );
  }





  // Contributing signals — ordered identically to Evidence Graph nodes
  const signalMap = new Map(allSignals.map((s) => [s.id, s]));
  const correlatedSignals = (incident.signal_ids || []).map((id) => {
    return signalMap.get(id) || { id, summary: 'Signal from cluster' };
  });

  const displaySignals = correlatedSignals.map((s, idx) => ({
    sno: idx + 1,
    id: s.id || `SIG-${idx + 1}`,
    timestamp: formatIST(s.timestamp),
    service: s.service ? `${s.service}:${s.component || 'core'}` : 'unknown-service',
    type: s.anomaly_type || 'ANOMALY',
    details: s.message || s.summary || 'Elevated anomaly metric over sliding baseline',
  }));

  const severityScore = (incident.severity || 0).toFixed(1);
  const confidenceScore = incident.confidence ? Math.round(incident.confidence * 100) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Breadcrumb & Incident Bento Header Row */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 4px' }}>
          <button
            onClick={() => onNavigate && onNavigate('dashboard')}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#565F6E',
              fontSize: '0.82rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            <ArrowLeft size={16} />
            <span>Back to Incidents</span>
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.74rem', color: '#565F6E' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#D6A62C' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
              {incident.created_at ? `INCIDENT DETECTED AT ${formatIST(incident.created_at)}` : 'AIOPS INCIDENT'}
            </span>
          </div>
        </div>

        {/* Bento Block 1: Incident Hero Card */}
        <div
          className="glass-card"
          style={{
            padding: '22px 28px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span
                className="font-mono"
                style={{
                  fontSize: '1.4rem',
                  fontWeight: 800,
                  color: '#252525',
                  letterSpacing: '-0.02em',
                }}
              >
                {incident.id}
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  padding: '3px 10px',
                  borderRadius: 'var(--radius-full)',
                  background: '#D6A62C',
                  color: '#FFFFFF',
                  fontWeight: 700,
                }}
              >
                INCIDENT
              </span>
            </div>

            <div style={{ width: '1px', height: '22px', background: 'var(--border-subtle)' }} />

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  padding: '4px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: (incident.severity || 0) > 70 ? 'rgba(186, 26, 26, 0.08)' : (incident.severity || 0) >= 50 ? 'rgba(214, 166, 44, 0.12)' : 'rgba(61, 70, 84, 0.08)',
                  border: (incident.severity || 0) > 70 ? '1px solid rgba(186, 26, 26, 0.3)' : (incident.severity || 0) >= 50 ? '1px solid rgba(214, 166, 44, 0.3)' : '1px solid rgba(61, 70, 84, 0.2)',
                  fontSize: '0.74rem',
                  fontWeight: 700,
                  color: (incident.severity || 0) > 70 ? '#BA1A1A' : (incident.severity || 0) >= 50 ? '#785A00' : '#3D4654',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: (incident.severity || 0) > 70 ? '#BA1A1A' : (incident.severity || 0) >= 50 ? '#D6A62C' : '#3D4654',
                  }}
                />
                SEV: {(incident.severity || 0) > 70 ? 'CRITICAL' : (incident.severity || 0) >= 50 ? 'HIGH' : 'MEDIUM'} {severityScore}
              </span>

              <span
                style={{
                  padding: '4px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  border: '1px solid rgba(61, 70, 84, 0.15)',
                  fontSize: '0.74rem',
                  fontWeight: 700,
                  color: '#3D4654',
                }}
              >
                {confidenceScore}% CONF
              </span>

              <span
                style={{
                  padding: '4px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.74rem',
                  color: '#565F6E',
                  fontWeight: 600,
                }}
              >
                {incident.environment?.toUpperCase() || 'PROD'}
              </span>

              {(incident.services && incident.services.length > 0) && (
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: 'var(--radius-full)',
                    background: '#FFFFFF',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.74rem',
                    fontFamily: 'var(--font-mono)',
                    color: '#252525',
                  }}
                >
                  {incident.services.join(', ')}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bento Block 2: Side-by-Side Scoring Panels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '18px',
        }}
      >
        {/* Severity Score Card */}
        <div
          className="glass-card"
          style={{
            padding: '24px 28px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#252525', margin: 0 }}>
              Severity Score
            </h2>
            <span
              style={{
                padding: '3px 10px',
                borderRadius: 'var(--radius-full)',
                background: Number(severityScore) > 70 ? 'rgba(186, 26, 26, 0.12)' : 'rgba(214, 166, 44, 0.18)',
                color: Number(severityScore) > 70 ? '#BA1A1A' : '#785A00',
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
              }}
            >
              {Number(severityScore) > 70 ? 'Critical' : Number(severityScore) >= 50 ? 'High' : 'Medium'} Tier
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
            <span style={{ fontSize: '3.2rem', fontWeight: 800, color: '#252525', lineHeight: 1, letterSpacing: '-0.02em' }}>
              {severityScore}
            </span>
            <span style={{ fontSize: '1.1rem', color: '#807663', fontWeight: 600 }}>/ 100</span>
          </div>
        </div>

        {/* Confidence Score Card */}
        <div
          className="glass-card"
          style={{
            padding: '24px 28px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#252525', margin: 0 }}>
            Confidence Score
          </h2>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
            <span style={{ fontSize: '3.2rem', fontWeight: 800, color: '#252525', lineHeight: 1, letterSpacing: '-0.02em' }}>
              {confidenceScore}%
            </span>
            <span style={{ fontSize: '1.1rem', color: '#3D4654', fontWeight: 700 }}>CERTAINTY</span>
          </div>
        </div>
      </div>

      {/* Bento Block 4: Contributing Telemetry Signals */}
      <div
        className="glass-card"
        style={{
          padding: '24px 28px',
          borderRadius: 'var(--radius-xl)',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#252525' }}>
              Contributing Telemetry Signals & Logs
            </h3>
            <span
              style={{
                fontSize: '0.72rem',
                padding: '3px 10px',
                borderRadius: 'var(--radius-full)',
                background: '#3D4654',
                color: '#FFFFFF',
                fontWeight: 600,
              }}
            >
              {displaySignals.length} Correlated Logs
            </span>
          </div>
        </div>

        <div style={{ overflowX: 'auto', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-subtle)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: '#3D4654', color: '#FFFFFF' }}>
                <th style={{ padding: '12px 14px', width: '52px', textAlign: 'center', fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>#</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Signal ID</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Timestamp</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Service / Component</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Type</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {displaySignals.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: '#565F6E' }}>
                    No correlated signals for this incident.
                  </td>
                </tr>
              ) : (
                displaySignals.map((sig, idx) => (
                <tr
                  key={sig.id + idx}
                  style={{
                    borderBottom: '1px solid rgba(61, 70, 84, 0.08)',
                    background: idx % 2 === 0 ? '#FAF8F0' : '#FFFFFF',
                  }}
                >
                  <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        background: '#3D4654',
                        color: '#FFFFFF',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                      }}
                      title={`Evidence Graph Node #${sig.sno}`}
                    >
                      {sig.sno}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#252525' }}>
                    {sig.id}
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', color: '#807663' }}>
                    {sig.timestamp}
                  </td>
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: '#252525' }}>
                    {sig.service}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span
                      style={{
                        fontSize: '0.68rem',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontWeight: 600,
                        background:
                          sig.type.includes('503') || sig.type.includes('FAIL')
                            ? 'rgba(186, 26, 26, 0.1)'
                            : '#EAE6DB',
                        color:
                          sig.type.includes('503') || sig.type.includes('FAIL')
                            ? '#BA1A1A'
                            : '#252525',
                      }}
                    >
                      {sig.type}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: '#565F6E' }}>
                    {sig.details}
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bento Block 5: Action Footer Bar */}
      <div
        className="glass-card"
        style={{
          padding: '16px 24px',
          borderRadius: 'var(--radius-xl)',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#565F6E', fontSize: '0.82rem' }}>
          <ShieldCheck size={18} color="#D6A62C" />
          <span>Autonomous gate validation chain verified. Ready for topological causal inspection.</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            className="btn btn-secondary"
            onClick={() => onNavigate && onNavigate('review')}
            style={{
              borderRadius: 'var(--radius-full)',
              padding: '8px 20px',
              fontSize: '0.82rem',
              background: '#FFFFFF',
              borderColor: 'rgba(61, 70, 84, 0.25)',
              color: '#252525',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <FileText size={15} color="#D6A62C" />
            <span>View Ticket for Approval</span>
          </button>

          <button
            className="btn btn-primary"
            onClick={() => onNavigate && onNavigate('graph')}
            style={{
              borderRadius: 'var(--radius-full)',
              padding: '8px 22px',
              fontSize: '0.82rem',
              background: '#D6A62C',
              color: '#FFFFFF',
            }}
          >
            <span>Explore Evidence Graph</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
