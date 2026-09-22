import React from 'react';
import { Activity, ShieldCheck, Filter, TrendingDown, Target, CheckCircle2 } from 'lucide-react';

export default function StatsBar({ signalsCount, incidents, jiraTicketsCount }) {
  const incidentCount = incidents.length;
  const totalSignalsInIncidents = incidents.reduce(
    (acc, inc) => acc + (inc.signal_ids ? inc.signal_ids.length : 0),
    0
  );

  // Noise reduction ratio calculation: (1 - incidents / signals) * 100
  const noiseReduction =
    signalsCount > 0 && incidentCount > 0
      ? Math.round((1 - incidentCount / signalsCount) * 100)
      : 0;

  // Filtered noise signals (signals not part of any incident)
  const filteredSignals = Math.max(0, signalsCount - totalSignalsInIncidents);

  // Average confidence across incidents
  const avgConfidence =
    incidentCount > 0
      ? (
          incidents.reduce((acc, inc) => acc + (inc.confidence || 0), 0) /
          incidentCount
        ).toFixed(2)
      : '0.00';

  const stats = [
    {
      label: 'Telemetry Signals',
      value: signalsCount,
      sub: 'Ingested anomalies',
      icon: Activity,
      color: 'var(--cyan)',
      glow: 'var(--cyan-glow)',
    },
    {
      label: 'Validated Incidents',
      value: incidentCount,
      sub: `${totalSignalsInIncidents} signals clustered`,
      icon: Target,
      color: 'var(--purple)',
      glow: 'var(--purple-glow)',
    },
    {
      label: 'Filtered Noise',
      value: filteredSignals,
      sub: 'Failed validation gates',
      icon: Filter,
      color: 'var(--amber)',
      glow: 'var(--amber-glow)',
    },
    {
      label: 'Noise Reduction',
      value: `${noiseReduction}%`,
      sub: 'Alert fatigue suppression',
      icon: TrendingDown,
      color: 'var(--green)',
      glow: 'var(--green-glow)',
    },
    {
      label: 'Avg Confidence',
      value: avgConfidence,
      sub: 'Multi-factor score',
      icon: ShieldCheck,
      color: 'var(--blue)',
      glow: 'var(--blue-glow)',
    },
    {
      label: 'Jira Tickets',
      value: jiraTicketsCount,
      sub: 'Human reviewed & published',
      icon: CheckCircle2,
      color: '#34D399',
      glow: 'rgba(52, 211, 153, 0.25)',
    },
  ];

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
      gap: '14px',
      margin: '24px 28px 20px 28px',
    }}>
      {stats.map((stat, i) => {
        const Icon = stat.icon;
        return (
          <div
            key={i}
            className="glass-card"
            style={{
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: 'var(--radius-md)',
                background: `rgba(${stat.color === 'var(--cyan)' ? '6,182,212' : stat.color === 'var(--purple)' ? '139,92,246' : stat.color === 'var(--amber)' ? '245,158,11' : stat.color === 'var(--green)' ? '16,185,129' : '59,130,246'}, 0.12)`,
                border: `1px solid ${stat.color}40`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Icon size={20} color={stat.color} />
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {stat.label}
              </div>
              <div style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                lineHeight: 1.2,
              }}>
                {stat.value}
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                {stat.sub}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
