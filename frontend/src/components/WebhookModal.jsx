import React, { useState } from 'react';
import { X, Zap, Send, Check, RefreshCw } from 'lucide-react';
import { api } from '../services/api';

const SAMPLE_CLOUDWATCH = {
  source: 'cloudwatch',
  AlarmName: 'High-Database-Connections-Payment',
  AlarmDescription: 'Database connection pool utilization exceeded 90%',
  Namespace: 'AWS/RDS',
  MetricName: 'DatabaseConnections',
  Timestamp: new Date().toISOString(),
  environment: 'prod',
  Trigger: {
    Dimensions: [{ name: 'DBInstanceIdentifier', value: 'payment-db-prod' }],
  },
};

const SAMPLE_GRAFANA = {
  source: 'grafana',
  title: 'OrderWorkerLatencySpike',
  alerts: [
    {
      status: 'firing',
      labels: {
        alertname: 'OrderWorkerLatencySpike',
        service: 'order',
        component: 'worker',
        environment: 'prod',
        severity: 'critical',
      },
      annotations: {
        description: 'Order worker execution latency is 4500ms (threshold 1000ms)',
      },
      startsAt: new Date().toISOString(),
      valueString: '4500ms',
    },
  ],
};

export default function WebhookModal({ isOpen, onClose, onWebhookSuccess }) {
  const [activeTab, setActiveTab] = useState('cloudwatch');
  const [payloadText, setPayloadText] = useState(
    JSON.stringify(SAMPLE_CLOUDWATCH, null, 2)
  );
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleTabChange = (type) => {
    setActiveTab(type);
    setResult(null);
    setError(null);
    if (type === 'cloudwatch') {
      setPayloadText(JSON.stringify(SAMPLE_CLOUDWATCH, null, 2));
    } else {
      setPayloadText(JSON.stringify(SAMPLE_GRAFANA, null, 2));
    }
  };

  const handleSend = async () => {
    setSending(true);
    setResult(null);
    setError(null);
    try {
      const parsed = JSON.parse(payloadText);
      const res = await api.testWebhook(parsed);
      setResult(res);
      if (onWebhookSuccess) {
        onWebhookSuccess(res);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px',
    }}>
      <div className="glass-card" style={{
        width: '100%',
        maxWidth: '620px',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-medium)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--shadow-lg)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap size={18} color="var(--amber)" />
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
              Simulate Live Ingestion Webhook
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleTabChange('cloudwatch')}
              className="btn btn-secondary"
              style={{
                fontSize: '0.8rem',
                padding: '6px 14px',
                background: activeTab === 'cloudwatch' ? 'var(--bg-card-active)' : 'transparent',
                borderColor: activeTab === 'cloudwatch' ? 'var(--cyan)' : 'var(--border-subtle)',
                color: activeTab === 'cloudwatch' ? 'var(--cyan)' : 'var(--text-secondary)',
              }}
            >
              AWS CloudWatch Alarm
            </button>
            <button
              onClick={() => handleTabChange('grafana')}
              className="btn btn-secondary"
              style={{
                fontSize: '0.8rem',
                padding: '6px 14px',
                background: activeTab === 'grafana' ? 'var(--bg-card-active)' : 'transparent',
                borderColor: activeTab === 'grafana' ? 'var(--purple)' : 'var(--border-subtle)',
                color: activeTab === 'grafana' ? 'var(--purple)' : 'var(--text-secondary)',
              }}
            >
              Grafana Alertmanager
            </button>
          </div>

          {/* JSON Textarea */}
          <textarea
            rows={10}
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
            className="font-mono"
            style={{
              width: '100%',
              padding: '12px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              fontSize: '0.78rem',
              lineHeight: 1.4,
              resize: 'vertical',
            }}
          />

          {error && (
            <div style={{ color: 'var(--rose)', fontSize: '0.8rem' }}>
              Error: {error}
            </div>
          )}

          {result && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--green)',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <Check size={16} />
              <span>
                Processed! Ingested {result.signals_ingested} signal(s) &bull; Correlated {result.new_incidents} incident(s).
              </span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 20px',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '10px',
        }}>
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          <button className="btn btn-primary" onClick={handleSend} disabled={sending}>
            {sending ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                <span>Ingesting...</span>
              </>
            ) : (
              <>
                <Send size={14} />
                <span>Dispatch Payload</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
