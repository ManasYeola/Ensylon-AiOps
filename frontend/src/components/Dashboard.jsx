import React, { useState } from 'react';
import { AlertCircle, ChevronRight, Layers, ShieldCheck, Database, Server, Clock, Hash } from 'lucide-react';

export default function Dashboard({
  incidents,
  selectedIncident,
  onSelectIncident,
  allSignals,
}) {
  const [filter, setFilter] = useState('all'); // all, high_sev, prod

  // Calculate rejected signals that don't belong to any accepted incident
  const acceptedSignalIds = new Set(
    incidents.flatMap((inc) => inc.signal_ids || [])
  );
  const rejectedSignals = allSignals.filter(
    (s) => !acceptedSignalIds.has(s.id)
  );

  const filteredIncidents = incidents.filter((inc) => {
    if (filter === 'high_sev') return (inc.severity || 0) >= 60;
    if (filter === 'prod') return inc.environment === 'prod';
    return true;
  });

  const getSeverityBadge = (sev) => {
    if (sev >= 70) return <span className="badge badge-rose">Critical ({sev.toFixed(1)})</span>;
    if (sev >= 50) return <span className="badge badge-amber">High ({sev.toFixed(1)})</span>;
    return <span className="badge badge-cyan">Medium ({sev.toFixed(1)})</span>;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Filter Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          {[
            { id: 'all', label: `All Incidents (${incidents.length})` },
            { id: 'high_sev', label: 'High / Critical (≥60)' },
            { id: 'prod', label: 'Production Only' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className="btn btn-secondary"
              style={{
                fontSize: '0.8rem',
                padding: '5px 12px',
                background: filter === tab.id ? 'var(--bg-card-active)' : 'transparent',
                borderColor: filter === tab.id ? 'var(--cyan)' : 'var(--border-subtle)',
                color: filter === tab.id ? 'var(--cyan)' : 'var(--text-secondary)',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          Click an incident to inspect details & evidence graph
        </span>
      </div>

      {/* Incidents List */}
      {filteredIncidents.length === 0 ? (
        <div className="glass-card" style={{ padding: '40px', textAlign: 'center' }}>
          <AlertCircle size={36} color="var(--cyan)" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '1.1rem', marginBottom: '6px' }}>No Active Incidents</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '440px', margin: '0 auto 16px' }}>
            Telemetry stream is clean. Click <strong>Run Pipeline Demo</strong> above to replay 18 sample anomaly signals and trigger correlation.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredIncidents.map((inc) => {
            const isSelected = selectedIncident?.id === inc.id;
            return (
              <div
                key={inc.id}
                onClick={() => onSelectIncident(inc)}
                className="glass-card"
                style={{
                  padding: '18px 22px',
                  cursor: 'pointer',
                  borderColor: isSelected ? 'var(--cyan)' : 'var(--border-subtle)',
                  background: isSelected
                    ? 'linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(18, 26, 45, 0.9) 100%)'
                    : 'var(--bg-glass)',
                  boxShadow: isSelected ? 'var(--shadow-glow-cyan)' : 'var(--shadow-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '16px',
                }}
              >
                {/* Left info */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="font-mono" style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                      {inc.id}
                    </span>
                    {getSeverityBadge(inc.severity || 0)}
                    <span className="badge badge-green">
                      Conf: {((inc.confidence || 0) * 100).toFixed(0)}%
                    </span>
                    <span className="badge badge-gray">
                      Env: {inc.environment}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '18px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Server size={14} color="var(--cyan)" />
                      <span>Services: <strong>{(inc.services || []).join(', ') || 'N/A'}</strong></span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Layers size={14} color="var(--purple)" />
                      <span><strong>{inc.signal_ids?.length || 0}</strong> signals correlated</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Hash size={14} color="var(--text-muted)" />
                      <span className="font-mono" style={{ fontSize: '0.75rem' }}>
                        FP: {(inc.fingerprint_id || '').substring(0, 10)}...
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right Arrow */}
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: isSelected ? 'var(--cyan)' : 'var(--bg-card-hover)',
                  color: isSelected ? '#000' : 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  transition: 'all 0.2s ease',
                }}>
                  <ChevronRight size={18} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Noise Rejection Drawer */}
      {rejectedSignals.length > 0 && (
        <div
          className="glass-card"
          style={{
            padding: '16px 20px',
            marginTop: '10px',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            background: 'rgba(245, 158, 11, 0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="badge badge-amber" style={{ fontSize: '0.7rem' }}>Noise Rejection Filter</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {rejectedSignals.length} Isolated / Outlier Signals Suppressed
              </span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Filtered out by 4 Validation Gates (low edge weight, env mismatch, or disconnected graph)
            </span>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {rejectedSignals.map((s) => (
              <div
                key={s.id}
                style={{
                  padding: '6px 12px',
                  background: 'var(--bg-card)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.78rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span className="font-mono" style={{ color: 'var(--amber)', fontWeight: 600 }}>{s.id}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{s.service}/{s.component}</span>
                <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>{s.type}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
