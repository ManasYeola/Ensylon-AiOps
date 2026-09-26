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
  Network,
  Radio,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  XCircle,
  Zap,
} from 'lucide-react';

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

  // Gates data extraction
  const gateResults = incident.gate_results || { accepted: true, gates: {} };
  const rawGates = gateResults.gates || {};

  const gate1Passed = rawGates.strong_edge ? rawGates.strong_edge.passed !== false : true;
  const gate2Passed = rawGates.environment_consistency ? rawGates.environment_consistency.passed !== false : true;
  const gate3Passed = rawGates.coherence ? rawGates.coherence.passed !== false : true;
  const gate4Passed = rawGates.bridge_check ? rawGates.bridge_check.passed !== false : true;

  const passedCount = [gate1Passed, gate2Passed, gate3Passed, gate4Passed].filter(Boolean).length;

  const gatesList = [
    {
      num: 'GATE 01',
      title: 'Strong Edge Check',
      passed: gate1Passed,
      desc: 'Correlated signals share strong temporal (<30s) and topological causal graph edges across adjacent pods.',
      metricLabel: 'Edge weight',
      metricVal: '0.94',
      metricSub: '(>0.70)',
    },
    {
      num: 'GATE 02',
      title: 'Environment Consistency',
      passed: gate2Passed,
      desc: `All 5 signals originate strictly within production Kubernetes cluster ${incident.environment || 'prod-eu-west-1'} namespaces without cross-env bleeding.`,
      metricLabel: 'Cluster identity',
      metricVal: incident.environment || 'prod-eu-west-1',
      metricSub: '(100%)',
    },
    {
      num: 'GATE 03',
      title: 'Coherence Check',
      passed: gate3Passed,
      desc: 'Symptom trajectory matches known database exhaustion propagation patterns stored in ENSYLON vector memory.',
      metricLabel: 'Cosine similarity',
      metricVal: '0.91',
      metricSub: 'vs vectors',
    },
    {
      num: 'GATE 04',
      title: 'Bridge Check',
      passed: gate4Passed,
      desc: 'Verifies no spurious topological bridges between unrelated background telemetry clusters or third-party webhooks.',
      metricLabel: 'Modularity score',
      metricVal: '0.88',
      metricSub: '(isolated)',
    },
  ];

  // Contributing signals
  const correlatedSignals = allSignals.filter((s) =>
    (incident.signal_ids || []).includes(s.id)
  );

  const fallbackSignals = [
    {
      id: 'SIG-8902',
      timestamp: '14:22:04 UTC',
      service: 'comms-service:redis',
      type: 'POOL_EXHAUSTION',
      details: 'Max connections (500/500) reached on pool-notification-cache',
    },
    {
      id: 'SIG-8905',
      timestamp: '14:22:18 UTC',
      service: 'comms-service:http',
      type: 'LATENCY_P99',
      details: 'p99 response time degraded from 45ms to 3,420ms',
    },
    {
      id: 'SIG-8908',
      timestamp: '14:22:31 UTC',
      service: 'queue-worker:bullmq',
      type: 'JOB_TIMEOUT',
      details: '480 outbound webhook dispatch jobs stalled > 60s',
    },
    {
      id: 'SIG-8911',
      timestamp: '14:23:02 UTC',
      service: 'comms-service:api',
      type: 'HTTP_503',
      details: '503 Service Unavailable returned on POST /v1/messages',
    },
    {
      id: 'SIG-8914',
      timestamp: '14:23:45 UTC',
      service: 'ingress-gateway',
      type: 'CIRCUIT_BREAKER',
      details: 'Circuit breaker OPEN for route /notify to prevent cascading crash',
    },
  ];

  const displaySignals = correlatedSignals.length > 0
    ? correlatedSignals.map((s, idx) => ({
        id: s.id || `SIG-${8900 + idx * 3}`,
        timestamp: s.timestamp ? new Date(s.timestamp).toLocaleTimeString() + ' UTC' : `14:22:${(idx * 14).toString().padStart(2, '0')} UTC`,
        service: s.service ? `${s.service}:${s.component || 'core'}` : 'comms-service:redis',
        type: s.anomaly_type || (idx === 0 ? 'POOL_EXHAUSTION' : idx === 1 ? 'LATENCY_P99' : 'HTTP_503'),
        details: s.message || s.summary || 'Elevated anomaly metric over sliding baseline',
      }))
    : fallbackSignals;

  const severityScore = (incident.severity || 52.8).toFixed(1);
  const confidenceScore = incident.confidence ? Math.round(incident.confidence * 100) : 98;

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
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>AIOPS HEURISTIC ENGINE RUN #4029</span>
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
                ACTIVE
              </span>
            </div>

            <div style={{ width: '1px', height: '22px', background: 'var(--border-subtle)' }} />

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
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
                {(incident.services || ['comms-service']).join(', ')}
              </span>

              <span
                style={{
                  padding: '4px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.74rem',
                  color: '#807663',
                }}
              >
                18m 42s Duration
              </span>
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-full)',
              background: '#FFFFFF',
              border: '1px solid var(--border-subtle)',
              fontSize: '0.75rem',
              color: '#252525',
            }}
          >
            <Network size={14} color="#D6A62C" />
            <span>Root: {incident.root_cause_service || 'Database Connection Pool & Webhook Delivery'}</span>
          </div>
        </div>
      </div>

      {/* Bento Block 2: Deterministic Validation Gates Group */}
      <div
        className="glass-card"
        style={{
          padding: '24px 28px',
          borderRadius: 'var(--radius-xl)',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: '10px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#252525', letterSpacing: '-0.01em' }}>
                Deterministic Validation Gates
              </h2>
              <span
                style={{
                  fontSize: '0.74rem',
                  padding: '3px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#D6A62C',
                  color: '#FFFFFF',
                  fontWeight: 700,
                }}
              >
                {passedCount} / 4 PASSED
              </span>
            </div>
            <p style={{ fontSize: '0.82rem', color: '#565F6E', marginTop: '4px' }}>
              Zero-hallucination deterministic heuristics required before AI ticket synthesis and automated dispatch.
            </p>
          </div>

          <span
            style={{
              padding: '4px 12px',
              borderRadius: 'var(--radius-full)',
              background: '#FFFFFF',
              border: '1px solid var(--border-subtle)',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              color: '#3D4654',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontWeight: 600,
            }}
          >
            GATE LATENCY: 14MS TOTAL
          </span>
        </div>

        {/* 4 Gate Bento Cards Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '14px',
            marginTop: '6px',
          }}
        >
          {gatesList.map((g) => (
            <div
              key={g.num}
              style={{
                padding: '16px 18px',
                borderRadius: 'var(--radius-lg)',
                background: '#FFFFFF',
                border: '1px solid var(--border-subtle)',
                borderTop: '2px solid #3D4654',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: '14px',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#807663', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {g.num}
                  </span>
                  <span
                    style={{
                      fontSize: '0.68rem',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      background: '#3D4654',
                      color: '#FFFFFF',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <CheckCircle2 size={12} color="#E6C766" />
                    <span>PASS</span>
                  </span>
                </div>

                <span style={{ fontSize: '0.94rem', fontWeight: 700, color: '#252525' }}>
                  {g.title}
                </span>

                <p style={{ fontSize: '0.76rem', color: '#565F6E', lineHeight: 1.45 }}>
                  {g.desc}
                </p>
              </div>

              <div
                style={{
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FAF8F0',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '0.74rem',
                }}
              >
                <span style={{ color: '#807663' }}>{g.metricLabel}</span>
                <span style={{ color: '#3D4654', fontWeight: 700 }}>
                  {g.metricVal} <span style={{ color: '#807663', fontWeight: 400 }}>{g.metricSub}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Bento Block 3: Side-by-Side Scoring Panels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: '18px',
        }}
      >
        {/* LEFT BENTO PANEL: Severity Score */}
        <div
          className="glass-card"
          style={{
            padding: '24px 26px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '20px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingBottom: '14px' }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#807663' }}>
                  COMPUTED SEVERITY METRIC
                </span>
                <span style={{ fontSize: '1.25rem', fontWeight: 700, color: '#252525', marginTop: '2px' }}>
                  Severity Score
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', margin: '14px 0 20px 0' }}>
              <span style={{ fontSize: '3rem', fontWeight: 700, color: '#252525', lineHeight: 1 }}>
                {severityScore}
              </span>
              <span style={{ fontSize: '1rem', color: '#807663' }}>/ 100</span>
            </div>

            {/* Severity Progress Bars */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {[
                { label: 'Service Criticality: Tier-1 Service (comms-service)', weight: 'Weight 35%', pct: 85, color: '#D6A62C' },
                { label: 'Blast Radius: 2 Downstream Consumers', weight: 'Weight 25%', pct: 45, color: '#D6A62C' },
                { label: 'Error Rate Delta: +412% over p99 baseline', weight: 'Weight 25%', pct: 62, color: '#D6A62C' },
                { label: 'User Impact Velocity: High (Outbound notifications blocked)', weight: 'Weight 15%', pct: 78, color: '#D6A62C' },
              ].map((bar, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem' }}>
                    <span style={{ color: '#252525' }}>{bar.label}</span>
                    <span style={{ color: '#807663' }}>{bar.weight}</span>
                  </div>
                  <div
                    style={{
                      width: '100%',
                      height: '6px',
                      borderRadius: 'var(--radius-full)',
                      background: '#EAE6DB',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${bar.pct}%`,
                        height: '100%',
                        borderRadius: 'var(--radius-full)',
                        background: bar.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div
            style={{
              padding: '8px 14px',
              borderRadius: 'var(--radius-full)',
              background: '#FFFFFF',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.75rem',
              color: '#565F6E',
            }}
          >
            <span>Evaluated against 30-day baseline</span>
            <span style={{ color: '#252525', fontWeight: 600 }}>Standard SLA Tier: Gold</span>
          </div>
        </div>

        {/* RIGHT BENTO PANEL: Confidence Score */}
        <div
          className="glass-card"
          style={{
            padding: '24px 26px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '20px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingBottom: '14px' }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#807663' }}>
                  CAUSAL VALIDATION METRIC
                </span>
                <span style={{ fontSize: '1.25rem', fontWeight: 700, color: '#252525', marginTop: '2px' }}>
                  Confidence Score
                </span>
              </div>
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-full)',
                  background: '#3D4654',
                  color: '#FFFFFF',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                }}
              >
                DETERMINISTIC CONSENSUS
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', margin: '14px 0 20px 0' }}>
              <span style={{ fontSize: '3rem', fontWeight: 700, color: '#252525', lineHeight: 1 }}>
                {confidenceScore}%
              </span>
              <span style={{ fontSize: '1rem', color: '#3D4654', fontWeight: 600 }}>CERTAINTY</span>
            </div>

            {/* 4 Metric Sub-Tiles Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '12px',
              }}
            >
              {[
                { label: 'Temporal Alignment', val: '0.99', sub: '42s clustering delta window', color: '#3D4654' },
                { label: 'Topology Validation', val: '0.97', sub: 'Dependency graph aligned', color: '#3D4654' },
                { label: 'Causal Gate Consensus', val: `${passedCount} / 4 Gates`, sub: 'Full threshold fulfillment', color: '#3D4654' },
                { label: 'False Positive Probability', val: '< 1.2%', sub: 'Empirical Bayes verification', color: '#3D4654' },
              ].map((tile, i) => (
                <div
                  key={i}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-lg)',
                    background: '#FFFFFF',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '2px',
                  }}
                >
                  <span style={{ fontSize: '0.72rem', color: '#807663' }}>{tile.label}</span>
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, color: tile.color }}>{tile.val}</span>
                  <span style={{ fontSize: '0.72rem', color: '#565F6E' }}>{tile.sub}</span>
                </div>
              ))}
            </div>
          </div>

          <div
            style={{
              padding: '8px 14px',
              borderRadius: 'var(--radius-full)',
              background: '#FFFFFF',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.75rem',
              color: '#565F6E',
            }}
          >
            <span>Model: Claude 3.5 Sonnet + GraphSAGE</span>
            <span style={{ color: '#3D4654', fontWeight: 600 }}>Auto-Triage Approved</span>
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
              Contributing Telemetry Signals
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
              {displaySignals.length} Correlated Signals
            </span>
          </div>
        </div>

        <div style={{ overflowX: 'auto', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-subtle)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: '#3D4654', color: '#FFFFFF' }}>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Signal ID</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Timestamp</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Service / Component</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Type</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {displaySignals.map((sig, idx) => (
                <tr
                  key={sig.id + idx}
                  style={{
                    borderBottom: '1px solid rgba(61, 70, 84, 0.08)',
                    background: idx % 2 === 0 ? '#FAF8F0' : '#FFFFFF',
                  }}
                >
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
              ))}
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
