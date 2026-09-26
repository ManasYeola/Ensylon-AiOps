import React from 'react';
import { Play, RefreshCw, Zap, Server, Cpu, ShieldCheck, User } from 'lucide-react';

export default function Header({
  health,
  isRunningDemo,
  onRunDemo,
  onOpenWebhook,
  onRefresh,
}) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 28px',
        borderBottom: '1px solid var(--border-subtle)',
        background: '#FAF8F0',
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}
    >
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h1
              style={{
                fontSize: '1.2rem',
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: '#252525',
              }}
            >
              ENSYLON AIOps
            </h1>
            <span
              style={{
                fontSize: '0.68rem',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
                background: '#EAE6DB',
                color: '#565F6E',
                fontWeight: 600,
              }}
            >
              MVP v0.1
            </span>
          </div>
          <p
            style={{
              fontSize: '0.72rem',
              color: '#565F6E',
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              marginTop: '1px',
            }}
          >
            Autonomous Incident Correlation
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* API Status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '5px 12px',
            background: '#FAF8F0',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
            fontSize: '0.78rem',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: health?.status === 'ok' ? '#10B981' : '#D6A62C',
              display: 'inline-block',
            }}
          />
          <span style={{ color: '#565F6E' }}>
            API: <strong style={{ color: '#252525' }}>{health?.status === 'ok' ? 'Active' : 'Standby'}</strong>
          </span>
        </div>

        {/* LLM Engine Badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '5px 12px',
            background: '#FAF8F0',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
            fontSize: '0.78rem',
          }}
        >
          <span style={{ color: '#565F6E' }}>
            LLM Engine: <strong style={{ color: '#252525' }}>Claude 3.5 Sonnet</strong>
          </span>
          <span
            style={{
              padding: '2px 6px',
              background: 'rgba(61, 70, 84, 0.1)',
              color: '#3D4654',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.68rem',
              fontWeight: 600,
            }}
          >
            Ready
          </span>
        </div>

        {/* Refresh Icon */}
        <button
          onClick={onRefresh}
          title="Refresh telemetry"
          style={{
            background: 'transparent',
            border: 'none',
            color: '#565F6E',
            cursor: 'pointer',
            padding: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <button
          className="btn btn-secondary"
          onClick={onOpenWebhook}
          style={{
            padding: '7px 16px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.82rem',
            borderColor: 'rgba(61, 70, 84, 0.35)',
            color: '#3D4654',
          }}
        >
          <span>Test Webhook</span>
        </button>

        <button
          className="btn btn-primary"
          onClick={onRunDemo}
          disabled={isRunningDemo}
          title="Run Pipeline Demo"
          style={{
            padding: '7px 18px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.82rem',
            background: '#D6A62C',
            color: '#FFFFFF',
          }}
        >
          {isRunningDemo ? (
            <>
              <RefreshCw size={15} className="animate-spin" />
              <span>Correlating Signals...</span>
            </>
          ) : (
            <span>Run Pipeline Demo</span>
          )}
        </button>

        {/* User Icon */}
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: '#785A00',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFFFFF',
            marginLeft: '4px',
          }}
        >
          <User size={16} />
        </div>
      </div>
    </header>
  );
}
