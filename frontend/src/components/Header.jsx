import React from 'react';
import { Play, RefreshCw, Zap, Server, Cpu, ShieldCheck } from 'lucide-react';

export default function Header({
  health,
  isRunningDemo,
  onRunDemo,
  onOpenWebhook,
  onRefresh,
}) {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '16px 28px',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'rgba(10, 15, 26, 0.85)',
      backdropFilter: 'blur(16px)',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <img src="/logo.svg" alt="Ensylon AIOps Logo" style={{ width: '38px', height: '38px' }} />
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 style={{
              fontSize: '1.25rem',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              background: 'linear-gradient(135deg, #FFFFFF 30%, #94A3B8 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              ENSYLON <span style={{ color: 'var(--cyan)' }}>AIOps</span>
            </h1>
            <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>MVP v0.1</span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Autonomous Incident Correlation &bull; 4-Gate Validation &bull; LLM Ticket Drafting
          </p>
        </div>
      </div>

      {/* Center Status Indicators */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
        {/* Backend health status */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 12px',
          background: 'var(--bg-glass-input)',
          borderRadius: 'var(--radius-full)',
          border: '1px solid var(--border-subtle)',
          fontSize: '0.78rem',
        }}>
          <div className="live-pulse" style={{
            background: health?.status === 'ok' ? 'var(--green)' : 'var(--rose)',
            boxShadow: health?.status === 'ok' ? '0 0 8px var(--green)' : '0 0 8px var(--rose)',
          }} />
          <span style={{ color: 'var(--text-secondary)' }}>API:</span>
          <span style={{ fontWeight: 600, color: health?.status === 'ok' ? 'var(--green)' : 'var(--rose)' }}>
            {health?.status === 'ok' ? 'ONLINE' : 'CONNECTING...'}
          </span>
        </div>

        {/* LLM Engine Badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          background: 'rgba(139, 92, 246, 0.1)',
          borderRadius: 'var(--radius-full)',
          border: '1px solid rgba(139, 92, 246, 0.25)',
          fontSize: '0.78rem',
        }}>
          <Cpu size={14} color="var(--purple)" />
          <span style={{ color: 'var(--text-secondary)' }}>LLM Engine:</span>
          <span style={{ fontWeight: 600, color: '#C4B5FD' }}>Groq / compound-mini</span>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <button
          className="btn btn-secondary"
          onClick={onRefresh}
          title="Refresh dashboard data"
          style={{ padding: '8px 12px' }}
        >
          <RefreshCw size={15} />
          <span>Refresh</span>
        </button>

        <button
          className="btn btn-secondary"
          onClick={onOpenWebhook}
          title="Simulate CloudWatch or Grafana payload"
        >
          <Zap size={15} color="var(--amber)" />
          <span>Test Webhook</span>
        </button>

        <button
          className="btn btn-primary"
          onClick={onRunDemo}
          disabled={isRunningDemo}
          title="Check Live Streams Status"
        >
          {isRunningDemo ? (
            <>
              <RefreshCw size={15} className="animate-spin" />
              <span>Checking Streams...</span>
            </>
          ) : (
            <>
              <Server size={15} />
              <span>Check Streams</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
}
