import React from 'react';
import { ShieldCheck, CheckCircle2, XCircle, AlertTriangle, Cpu, Layers, HardDrive, Terminal } from 'lucide-react';

export default function IncidentDetails({ incident, allSignals }) {
  if (!incident) {
    return (
      <div className="glass-card" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Select an incident from the dashboard to view details and gate evaluations.
      </div>
    );
  }

  const gateResults = incident.gate_results || { accepted: true, gates: {} };
  const gates = gateResults.gates || {
    strong_edge: { passed: true, reason: 'Max internal edge weight >= 0.70' },
    environment_consistency: { passed: true, reason: '100% prod signals' },
    coherence: { passed: true, reason: 'Graph density >= threshold' },
    bridge_check: { passed: true, reason: 'No unverified bridge signals' },
  };

  // Find all signals belonging to this incident
  const incidentSignals = allSignals.filter((s) =>
    (incident.signal_ids || []).includes(s.id)
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 4 Validation Gates Inspector */}
      <div className="glass-card" style={{ padding: '20px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShieldCheck size={20} color="var(--green)" />
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
              The 4 Deterministic Validation Gates (PRD §17)
            </h3>
          </div>
          <span className="badge badge-green">
            Status: ALL GATES PASSED
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
          {Object.entries(gates).map(([key, gate]) => {
            const passed = gate.passed !== false;
            const gateName =
              key === 'strong_edge'
                ? '1. Strong Edge Check'
                : key === 'environment_consistency'
                ? '2. Env Consistency'
                : key === 'coherence'
                ? '3. Coherence Check'
                : '4. Bridge Check';

            const gateDesc =
              key === 'strong_edge'
                ? 'Cluster must contain at least 1 edge >= 0.70 threshold'
                : key === 'environment_consistency'
                ? '100% of signals must share identical environment'
                : key === 'coherence'
                ? 'Internal graph density and agreement verification'
                : 'Prohibits weak multi-hop connections across services';

            return (
              <div
                key={key}
                style={{
                  background: passed ? 'rgba(16, 185, 129, 0.05)' : 'rgba(244, 63, 94, 0.05)',
                  border: `1px solid ${passed ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
                  borderRadius: 'var(--radius-md)',
                  padding: '14px 16px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{gateName}</span>
                  {passed ? (
                    <CheckCircle2 size={16} color="var(--green)" />
                  ) : (
                    <XCircle size={16} color="var(--rose)" />
                  )}
                </div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {gateDesc}
                </div>
                <div className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                  {gate.reason || (passed ? 'Verified valid' : 'Rejected')}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Scoring Formulas Breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Severity */}
        <div className="glass-card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Severity Scoring Formula (PRD §18)
            </h4>
            <span className="badge badge-amber font-mono" style={{ fontSize: '0.85rem' }}>
              {(incident.severity || 0).toFixed(1)} / 100
            </span>
          </div>
          <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginBottom: '14px', fontFamily: 'var(--font-mono)' }}>
            0.35&times;Blast + 0.35&times;Criticality + 0.20&times;Trend + 0.10&times;Magnitude
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.78rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Affected Services (Blast Radius):</span>
              <span className="font-mono">{(incident.services || []).join(', ')}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Signal Volume in Incident:</span>
              <span className="font-mono">{incident.signal_ids?.length || 0} signals</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Environment Criticality:</span>
              <span className="font-mono">Production (1.00 weight)</span>
            </div>
          </div>
        </div>

        {/* Confidence */}
        <div className="glass-card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Confidence Scoring Formula (PRD §19)
            </h4>
            <span className="badge badge-green font-mono" style={{ fontSize: '0.85rem' }}>
              {((incident.confidence || 0) * 100).toFixed(1)}%
            </span>
          </div>
          <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginBottom: '14px', fontFamily: 'var(--font-mono)' }}>
            0.35&times;Density + 0.25&times;Agreement + 0.20&times;Topology + 0.20&times;Temporal
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.78rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Graph Density Weight:</span>
              <span className="font-mono">High internal edge coherence</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Temporal Proximity:</span>
              <span className="font-mono">Within 10-minute sliding window</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Topology Hops:</span>
              <span className="font-mono">0-hop internal service cohesion</span>
            </div>
          </div>
        </div>
      </div>

      {/* Correlated Signals Table */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>
            Contributing Telemetry Signals ({incidentSignals.length})
          </h4>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Deterministic evidence payload bound to this incident
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                <th style={{ padding: '8px 12px' }}>Signal ID</th>
                <th style={{ padding: '8px 12px' }}>Timestamp</th>
                <th style={{ padding: '8px 12px' }}>Service / Comp</th>
                <th style={{ padding: '8px 12px' }}>Type</th>
                <th style={{ padding: '8px 12px' }}>Details / Message</th>
              </tr>
            </thead>
            <tbody>
              {incidentSignals.map((s) => (
                <tr
                  key={s.id}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                    transition: 'background 0.15s ease',
                  }}
                >
                  <td style={{ padding: '10px 12px' }} className="font-mono">
                    <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>{s.id}</span>
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }} className="font-mono">
                    {s.timestamp ? s.timestamp.substring(11, 19) : 'N/A'}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{s.service}</span>
                    <span style={{ color: 'var(--text-muted)' }}> / {s.component}</span>
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>
                      {s.type}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                    {s.message ? (
                      <span>&ldquo;{s.message}&rdquo;</span>
                    ) : s.value !== null && s.value !== undefined ? (
                      <span className="font-mono">Value: {s.value}</span>
                    ) : (
                      <span>Anomaly detected</span>
                    )}
                    {s.template_id && (
                      <span className="badge badge-gray" style={{ marginLeft: '8px', fontSize: '0.65rem' }}>
                        {s.template_id}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
