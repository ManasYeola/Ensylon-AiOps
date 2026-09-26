import React, { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  Cpu,
  Database,
  FileText,
  Filter,
  Layers,
  Radio,
  RefreshCw,
  Route,
  Server,
  ShieldCheck,
  Sliders,
  Sparkles,
  TrendingUp,
  Webhook,
  Zap,
} from 'lucide-react';
import StatsBar from './StatsBar';

export default function Dashboard({
  incidents = [],
  selectedIncident,
  onSelectIncident,
  allSignals = [],
  jiraTicketsCount = 0,
  onNavigate,
}) {
  const [filter, setFilter] = useState('all'); // default to all so user sees all incidents!
  const [timeRange, setTimeRange] = useState('Last 6 hours');
  const [isRefreshingNoise, setIsRefreshingNoise] = useState(false);

  // Accepted signals
  const acceptedSignalIds = new Set(
    incidents.flatMap((inc) => inc.signal_ids || [])
  );
  
  // Unclustered / Suppressed signals
  const rejectedSignals = allSignals.filter(
    (s) => !acceptedSignalIds.has(s.id)
  );

  // Filtered incidents
  const filteredIncidents = incidents.filter((inc) => {
    if (filter === 'critical') return (inc.severity || 0) > 70;
    if (filter === 'high') return (inc.severity || 0) <= 70;
    if (filter === 'prod') return inc.environment === 'prod' || !inc.environment;
    return true; // 'all'
  });

  // Current primary incident to show in the Hero Card
  const heroIncident = selectedIncident || (incidents.length > 0 ? incidents[0] : null);

  const handleRefreshNoise = () => {
    setIsRefreshingNoise(true);
    setTimeout(() => {
      setIsRefreshingNoise(false);
    }, 600);
  };

  const noiseItems =
    rejectedSignals.length > 0
      ? rejectedSignals.slice(0, 6).map((s, idx) => ({
          id: s.id || `SIG-${idx + 1}`,
          title: s.message || s.summary || `${s.service || 'service'}: transient anomaly`,
          metric: s.metric_value ? `${s.metric_value} delta` : 'sub-threshold',
          badge: idx % 3 === 0 ? 'Isolated Spike' : idx % 3 === 1 ? 'Sub-threshold' : 'Transient Jitter',
          time: `${(idx + 1) * 4}m ago`,
        }))
      : [];

  const outlierCount = rejectedSignals.length;

  const critCount = incidents.filter((i) => (i.severity || 0) > 70).length;
  const highCount = incidents.filter((i) => (i.severity || 0) <= 70).length;
  const prodCount = incidents.filter((i) => i.environment === 'prod' || !i.environment).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Bento Top Control Bar (Pills & Time Range) */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        {/* Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          {[
            { id: 'all', label: `All Incidents (${incidents.length})`, hasPulse: true },
            { id: 'critical', label: `Critical Severity (>70) (${critCount})` },
            { id: 'high', label: `High / Medium (≤70) (${highCount})` },
            { id: 'prod', label: `Production Only (${prodCount})` },
          ].map((btn) => {
            const isActive = filter === btn.id;
            return (
              <button
                key={btn.id}
                onClick={() => setFilter(btn.id)}
                style={{
                  padding: '8px 18px',
                  borderRadius: 'var(--radius-full)',
                  fontSize: '0.82rem',
                  fontWeight: isActive ? 600 : 500,
                  background: isActive ? '#3D4654' : '#FAF8F0',
                  color: isActive ? '#FAF8F0' : '#565F6E',
                  border: isActive ? '1px solid #3D4654' : '1px solid var(--border-subtle)',
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                }}
              >
                {btn.hasPulse && (
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: '#D6A62C',
                      display: 'inline-block',
                    }}
                  />
                )}
                <span>{btn.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Bento Master Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(12, 1fr)',
          gap: '18px',
        }}
      >
        {/* Bento Cell 1: Hero Active Incident Card (Spans 8 cols on desktop) */}
        <div
          id="hero-incident-card"
          className="glass-card"
          style={{
            gridColumn: 'span 8',
            padding: '24px 28px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '18px',
          }}
        >
          {heroIncident ? (
            <>
              <div>
                {/* Header Row */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '10px',
                    marginBottom: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: '1.3rem',
                        fontWeight: 700,
                        color: '#252525',
                        letterSpacing: '-0.01em',
                      }}
                    >
                      {heroIncident.id}
                    </span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        background: '#EAE6DB',
                        color: '#565F6E',
                        fontWeight: 600,
                      }}
                    >
                      {heroIncident.environment?.toUpperCase() || 'PROD'}
                    </span>
                    <span
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '0.78rem',
                        color: '#807663',
                      }}
                    >
                      <Clock size={13} />
                      <span>14 mins ago</span>
                    </span>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '0.75rem',
                      color: '#565F6E',
                      padding: '4px 12px',
                      background: '#FFFFFF',
                      borderRadius: 'var(--radius-full)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <Server size={13} color="#807663" />
                    <span>{heroIncident.cluster_id || heroIncident.environment || heroIncident.id}</span>
                  </div>
                </div>

                {/* Key Badges Bar */}
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                  <div
                    style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-full)',
                      background: (heroIncident.severity || 0) > 70 ? '#BA1A1A' : (heroIncident.severity || 0) >= 50 ? '#D6A62C' : '#3D4654',
                      color: '#FFFFFF',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                    }}
                  >
                    <AlertTriangle size={14} color="#FFFFFF" />
                    <span>
                      {(heroIncident.severity || 0) > 70 ? 'CRITICAL' : (heroIncident.severity || 0) >= 50 ? 'HIGH' : 'MEDIUM'}{' '}
                      {(heroIncident.severity || 0).toFixed(1)} / 100
                    </span>
                  </div>

                  <div
                    style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-full)',
                      background: '#FFFFFF',
                      border: '1px solid var(--border-subtle)',
                      color: '#785A00',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                    }}
                  >
                    <ShieldCheck size={14} color="#785A00" />
                    <span>
                      CONF {heroIncident.confidence != null ? Math.round(heroIncident.confidence <= 1 ? heroIncident.confidence * 100 : heroIncident.confidence) : 0}%
                    </span>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-full)',
                      background: '#FFFFFF',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.78rem',
                      fontFamily: 'var(--font-mono)',
                      color: '#252525',
                    }}
                  >
                    <Webhook size={13} color="#807663" />
                    <span>{(heroIncident.services || ['comms-service']).join(', ')}</span>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-full)',
                      background: '#FFFFFF',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.75rem',
                      color: '#565F6E',
                    }}
                  >
                    <Sparkles size={13} color="#D6A62C" />
                    <span>{heroIncident.signal_ids ? heroIncident.signal_ids.length : 5} signals correlated</span>
                  </div>
                </div>

                {/* Narrative Context & Fingerprint Card */}
                <div
                  style={{
                    padding: '16px 20px',
                    borderRadius: 'var(--radius-lg)',
                    background: '#FFFFFF',
                    border: '1px solid var(--border-subtle)',
                    marginBottom: '16px',
                  }}
                >
                  <p
                    style={{
                      fontSize: '0.98rem',
                      fontWeight: 600,
                      color: '#252525',
                      lineHeight: 1.45,
                      marginBottom: '10px',
                    }}
                  >
                    {heroIncident.summary ||
                      heroIncident.title ||
                      'Cascading latency spike on Redis connection pool affecting outbound webhook delivery'}
                  </p>

                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      gap: '16px',
                      fontSize: '0.75rem',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ color: '#807663', fontFamily: 'var(--font-sans)' }}>Fingerprint:</span>
                      <span
                        style={{
                          background: '#FAF8F0',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border-subtle)',
                          color: '#252525',
                        }}
                      >
                        {heroIncident.fingerprint ? `${heroIncident.fingerprint.slice(0, 13)}...` : 'dbdf6dca81f49...e21a'}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ color: '#807663', fontFamily: 'var(--font-sans)' }}>Primary Root:</span>
                      <span style={{ color: '#D6A62C', fontWeight: 700 }}>
                        {heroIncident.root_cause_service || 'redis-cluster-master-02:6379'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom Action Ribbon */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: '#565F6E' }}>
                  <ShieldCheck size={16} color="#785A00" />
                  <span style={{ fontWeight: 500 }}>
                    3 Validation Gates Passed &bull; Ready for Ticket Creation
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    className="btn btn-secondary"
                    onClick={() => {
                      onSelectIncident(heroIncident);
                      if (onNavigate) onNavigate('details');
                    }}
                    style={{
                      padding: '8px 18px',
                      borderRadius: 'var(--radius-full)',
                      fontSize: '0.82rem',
                      background: '#FFFFFF',
                      borderColor: 'rgba(61, 70, 84, 0.25)',
                      color: '#252525',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span>Investigate</span>
                    <ArrowRight size={14} />
                  </button>

                  <button
                    className="btn btn-primary"
                    onClick={() => {
                      onSelectIncident(heroIncident);
                      if (onNavigate) onNavigate('review');
                    }}
                    style={{
                      padding: '8px 20px',
                      borderRadius: 'var(--radius-full)',
                      fontSize: '0.82rem',
                      fontWeight: 700,
                      background: '#D6A62C',
                      color: '#FFFFFF',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <FileText size={14} />
                    <span>View Ticket</span>
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div style={{ padding: '30px', textAlign: 'center', color: '#565F6E' }}>
              No incidents available. Awaiting streaming telemetry anomalies.
            </div>
          )}
        </div>

        {/* Bento Cell 3: Compact Side Metric Cluster (Spans 4 cols on desktop) */}
        <div style={{ gridColumn: 'span 4' }}>
          <StatsBar
            signalsCount={allSignals.length}
            incidents={incidents}
            jiraTicketsCount={jiraTicketsCount}
            outlierCount={outlierCount}
          />
        </div>

        {/* Bento Cell 4: All Correlated Incidents Registry (Spans 12 cols) */}
        <div
          className="glass-card"
          style={{
            gridColumn: 'span 12',
            padding: '24px 28px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
              paddingBottom: '14px',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '34px',
                  height: '34px',
                  borderRadius: 'var(--radius-full)',
                  background: 'rgba(214, 166, 44, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#785A00',
                }}
              >
                <Layers size={18} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#252525' }}>
                    All Correlated Incidents
                  </h3>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      background: '#3D4654',
                      color: '#FFFFFF',
                    }}
                  >
                    {filteredIncidents.length} Clusters
                  </span>
                </div>
                <p style={{ fontSize: '0.78rem', color: '#565F6E', marginTop: '2px' }}>
                  Click any incident cluster to select it, update the Evidence Graph, or jump into Gates & Jira dispatch.
                </p>
              </div>
            </div>

            <span style={{ fontSize: '0.75rem', color: '#807663' }}>
              Showing {filteredIncidents.length} of {incidents.length} total incidents
            </span>
          </div>

          {/* Incidents Table / Cards Feed */}
          {filteredIncidents.length === 0 ? (
            <div style={{ padding: '36px', textAlign: 'center', color: '#565F6E' }}>
              <p style={{ fontSize: '0.9rem', fontWeight: 600 }}>No incidents match the "{filter}" filter.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {filteredIncidents.map((inc) => {
                const isSelected = (selectedIncident?.id || heroIncident?.id) === inc.id;
                const isCrit = (inc.severity || 0) > 70;
                const isHigh = (inc.severity || 0) >= 50 && !isCrit;

                return (
                  <div
                    key={inc.id}
                    onClick={() => {
                      onSelectIncident(inc);
                      document.getElementById('hero-incident-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '14px',
                      padding: '14px 20px',
                      borderRadius: 'var(--radius-lg)',
                      background: isSelected ? '#FFFDF7' : '#FFFFFF',
                      border: isSelected ? '2px solid #D6A62C' : '1px solid var(--border-subtle)',
                      boxShadow: isSelected ? '0 0 0 1px #D6A62C, var(--shadow-sm)' : 'var(--shadow-sm)',
                      cursor: 'pointer',
                      transition: 'all var(--transition-fast)',
                    }}
                  >
                    {/* Left: ID & Metadata */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: '240px' }}>
                      <span
                        style={{
                          width: '10px',
                          height: '10px',
                          borderRadius: '50%',
                          background: isSelected ? '#D6A62C' : 'rgba(61, 70, 84, 0.25)',
                          flexShrink: 0,
                        }}
                      />
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span
                            className="font-mono"
                            style={{
                              fontSize: '0.95rem',
                              fontWeight: 700,
                              color: '#252525',
                            }}
                          >
                            {inc.id}
                          </span>
                          <span
                            style={{
                              fontSize: '0.68rem',
                              padding: '1px 7px',
                              borderRadius: 'var(--radius-full)',
                              background: '#EAE6DB',
                              color: '#565F6E',
                              fontWeight: 600,
                            }}
                          >
                            {inc.environment?.toUpperCase() || 'PROD'}
                          </span>
                          {isSelected && (
                            <span
                              style={{
                                fontSize: '0.65rem',
                                fontWeight: 700,
                                padding: '1px 8px',
                                borderRadius: 'var(--radius-full)',
                                background: 'rgba(214, 166, 44, 0.2)',
                                color: '#785A00',
                                border: '1px solid #D6A62C',
                              }}
                            >
                              CURRENTLY SELECTED
                            </span>
                          )}
                        </div>
                        <span style={{ fontSize: '0.74rem', color: '#565F6E' }}>
                          Root: <strong style={{ color: '#252525' }}>{inc.root_cause_service || (inc.services || ['unknown'])[0]}</strong>
                        </span>
                      </div>
                    </div>

                    {/* Middle: Badges & Summary */}
                    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px', flex: 1, minWidth: '280px' }}>
                      <span
                        style={{
                          fontSize: '0.74rem',
                          fontWeight: 700,
                          padding: '3px 10px',
                          borderRadius: 'var(--radius-full)',
                          background: isCrit ? '#BA1A1A' : isHigh ? '#D6A62C' : '#3D4654',
                          color: '#FFFFFF',
                        }}
                      >
                        {isCrit ? 'CRITICAL' : isHigh ? 'HIGH' : 'MEDIUM'} {(inc.severity || 0).toFixed(1)}
                      </span>

                      <span
                        style={{
                          fontSize: '0.74rem',
                          padding: '3px 10px',
                          borderRadius: 'var(--radius-full)',
                          background: '#F4F1E8',
                          color: '#785A00',
                          border: '1px solid var(--border-subtle)',
                          fontWeight: 600,
                        }}
                      >
                        CONF {inc.confidence ? `${Math.round(inc.confidence * 100)}%` : '98%'}
                      </span>

                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '0.74rem',
                          fontFamily: 'var(--font-mono)',
                          color: '#565F6E',
                          padding: '3px 10px',
                          borderRadius: 'var(--radius-full)',
                          background: '#F4F1E8',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <Webhook size={12} color="#807663" />
                        <span>{(inc.services || []).join(', ') || 'comms-service'}</span>
                      </div>

                      <span style={{ fontSize: '0.74rem', color: '#807663' }}>
                        &bull; {inc.signal_ids ? inc.signal_ids.length : 5} signals
                      </span>
                    </div>

                    {/* Right: Action Buttons */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        className="btn btn-secondary"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectIncident(inc);
                          if (onNavigate) onNavigate('details');
                        }}
                        style={{
                          padding: '6px 14px',
                          borderRadius: 'var(--radius-full)',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          background: '#FAF8F0',
                          color: '#252525',
                          borderColor: 'rgba(61, 70, 84, 0.25)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '5px',
                        }}
                      >
                        <span>Investigate</span>
                        <ArrowRight size={13} />
                      </button>

                      <button
                        className="btn btn-primary"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectIncident(inc);
                          if (onNavigate) onNavigate('review');
                        }}
                        style={{
                          padding: '6px 14px',
                          borderRadius: 'var(--radius-full)',
                          fontSize: '0.78rem',
                          fontWeight: 700,
                          background: isSelected ? '#D6A62C' : '#FAF8F0',
                          color: isSelected ? '#FFFFFF' : '#785A00',
                          borderColor: '#D6A62C',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '5px',
                        }}
                      >
                        <FileText size={13} color={isSelected ? '#FFFFFF' : '#785A00'} />
                        <span>View Ticket</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Bento Cell 5: Filtered Telemetry Noise Stream (Spans 12 cols on desktop) */}
        <div
          className="glass-card"
          style={{
            gridColumn: 'span 12',
            padding: '22px 24px',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '14px',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '10px',
              paddingBottom: '10px',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#565F6E',
                }}
              >
                <Sliders size={16} />
              </div>
              <div>
                <h3 style={{ fontSize: '0.94rem', fontWeight: 700, color: '#252525' }}>
                  Suppression Telemetry Stream
                </h3>
                <p style={{ fontSize: '0.74rem', color: '#565F6E' }}>
                  Continuous evaluation of unclustered transient pulses
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.74rem',
                  padding: '3px 12px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  color: '#565F6E',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {outlierCount} outliers
              </span>
              <button
                onClick={handleRefreshNoise}
                title="Re-evaluate thresholds"
                style={{
                  padding: '6px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FFFFFF',
                  border: '1px solid var(--border-subtle)',
                  color: '#565F6E',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <RefreshCw size={14} className={isRefreshingNoise ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>

          {/* Outlier Stream Rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {noiseItems.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#565F6E', fontSize: '0.85rem' }}>
                No suppressed signals recorded.
              </div>
            ) : (
              noiseItems.map((item, idx) => (
                <div
                  key={item.id + idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    borderRadius: 'var(--radius-md)',
                    background: '#FFFFFF',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.78rem',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        padding: '2px 10px',
                        borderRadius: 'var(--radius-full)',
                        background: '#3D4654',
                        color: '#FFFFFF',
                      }}
                    >
                      {item.id}
                    </span>
                    <span
                      style={{
                        color: '#252525',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.title}{' '}
                      <span style={{ color: '#807663', fontFamily: 'var(--font-mono)' }}>
                        ({item.metric})
                      </span>
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        background: '#FAF8F0',
                        color: '#565F6E',
                        fontWeight: 500,
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      {item.badge}
                    </span>
                    <span style={{ color: '#807663', fontSize: '0.72rem' }}>
                      {item.time}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
