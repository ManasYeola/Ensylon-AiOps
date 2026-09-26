import React from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Filter,
  ShieldCheck,
  Sliders,
  TrendingUp,
  Zap,
} from 'lucide-react';

export default function StatsBar({
  signalsCount = 0,
  incidents = [],
  jiraTicketsCount = 0,
  outlierCount = 0,
}) {
  const incidentCount = incidents.length;
  const activeIncidents = incidents.filter((i) => i.status !== 'resolved').length;

  // Noise reduction ratio calculation
  const noiseReductionRatio =
    signalsCount > 0 && incidentCount > 0
      ? Math.max(0, Math.min(99.9, ((1 - incidentCount / signalsCount) * 100))).toFixed(1)
      : '0.0';

  // Average confidence across incidents
  const avgConfidence =
    incidentCount > 0
      ? (
          (incidents.reduce((acc, inc) => acc + (inc.confidence || 0), 0) / incidentCount) * 100
        ).toFixed(1)
      : '0.0';

  const displaySignals = (signalsCount || 0).toLocaleString();
  const displayFilteredNoise = (outlierCount || 0).toLocaleString();

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        gap: '12px',
        height: '100%',
      }}
    >
      {/* Card 1: Telemetry Signals */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            SIGNALS
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Activity size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
            {displaySignals}
          </span>
        </div>
      </div>

      {/* Card 2: Validated Incidents */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            INCIDENTS
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <AlertTriangle size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
              {activeIncidents}
            </span>
            <span
              style={{
                fontSize: '0.66rem',
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: activeIncidents > 0 ? '#D6A62C' : '#807663',
                color: '#FFFFFF',
                fontWeight: 600,
              }}
            >
              {activeIncidents > 0 ? 'Active' : 'None'}
            </span>
          </div>
        </div>
      </div>

      {/* Card 3: Filtered Noise */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            FILTERED NOISE
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Filter size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
            {displayFilteredNoise}
          </span>
        </div>
      </div>

      {/* Card 4: Noise Reduction Percentage */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            NOISE REDUCTION
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Sliders size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
            {noiseReductionRatio}%
          </span>
        </div>
      </div>

      {/* Card 5: Avg Confidence */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            CONFIDENCE
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ShieldCheck size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
            {avgConfidence}%
          </span>
        </div>
      </div>

      {/* Card 6: Jira Tickets */}
      <div
        className="glass-card"
        style={{
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#565F6E' }}>
            JIRA TICKETS
          </span>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(61, 70, 84, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <FileText size={15} color="#3D4654" />
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '1.45rem', fontWeight: 700, color: '#3D4654', letterSpacing: '-0.02em' }}>
              {jiraTicketsCount || 0}
            </span>
            <span
              style={{
                fontSize: '0.66rem',
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: jiraTicketsCount > 0 ? '#10B981' : '#EAE6DB',
                color: jiraTicketsCount > 0 ? '#FFFFFF' : '#565F6E',
                fontWeight: 600,
              }}
            >
              Published
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
