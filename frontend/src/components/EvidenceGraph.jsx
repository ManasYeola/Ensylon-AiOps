import React, { useState, useMemo } from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Crosshair,
  Database,
  Download,
  Eye,
  FileDown,
  Info,
  Layers,
  Maximize2,
  Network,
  Radio,
  RefreshCw,
  Server,
  Shield,
  ShieldCheck,
  Sliders,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

export default function EvidenceGraph({ incident, graphData, onNavigate }) {
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [viewMode, setViewMode] = useState('topo'); // topo, time, latency

  // Default fallback sample nodes if live telemetry has no graph data yet
  const fallbackNodes = useMemo(
    () => [
      {
        id: 'SIG-8902',
        service: 'comms-service',
        component: 'redis',
        timestamp: '2026-09-26T14:22:04.112Z',
        anomaly_type: 'ResourceStarvation::PoolExhaustion',
        source: 'Datadog / Prometheus Redis Exporter',
        message:
          'Connection pool starved due to unclosed socket leak during batch SMS dispatch. Pool exhaustion triggered cascading backpressure across comms-service workers.',
        role: 'ROOT CAUSE',
      },
      {
        id: 'SIG-8905',
        service: 'comms-service',
        component: 'http',
        timestamp: '2026-09-26T14:22:18.420Z',
        anomaly_type: 'PerformanceDegradation::P99Spike',
        source: 'OpenTelemetry Trace Aggregator',
        message:
          'P99 latency surged from 45ms to 3,420ms due to blocked thread pool awaiting redis connections. Triggered circuit alerts in ingress proxy.',
        role: 'DOWNSTREAM',
      },
      {
        id: 'SIG-8908',
        service: 'queue-worker',
        component: 'bullmq',
        timestamp: '2026-09-26T14:22:23.018Z',
        anomaly_type: 'QueueCongestion::Backpressure',
        source: 'Kubernetes Pod Diagnostics',
        message:
          'Celery/BullMQ consumers failed to write status acknowledgments back to storage, causing worker thread pool to hit max capacity of 128/128.',
        role: 'DOWNSTREAM',
      },
      {
        id: 'SIG-8911',
        service: 'comms-service',
        component: 'api',
        timestamp: '2026-09-26T14:22:26.504Z',
        anomaly_type: 'ServiceUnavailability::HTTP503',
        source: 'Envoy Access Logs',
        message:
          'Public HTTP ingress responded with 503 Service Unavailable to 41.2% of inbound traffic as internal queue buffers reached hard limits.',
        role: 'SYMPTOM',
      },
      {
        id: 'SIG-8914',
        service: 'ingress-gateway',
        component: 'istio-proxy',
        timestamp: '2026-09-26T14:22:34.901Z',
        anomaly_type: 'TrafficManagement::CircuitBreak',
        source: 'Istio Service Mesh Metrics',
        message:
          'Ingress Envoy proxy automatically tripped outlier detection breaker, shedding 60% of non-essential dispatch routes to prevent whole-cluster cascading failure.',
        role: 'ISOLATION BOUNDARY',
      },
    ],
    []
  );

  const fallbackEdges = useMemo(
    () => [
      { source_signal: 'SIG-8902', target_signal: 'SIG-8905', correlation_score: 0.96, delta_seconds: 14 },
      { source_signal: 'SIG-8902', target_signal: 'SIG-8908', correlation_score: 0.94, delta_seconds: 19 },
      { source_signal: 'SIG-8905', target_signal: 'SIG-8911', correlation_score: 0.88, delta_seconds: 3 },
      { source_signal: 'SIG-8908', target_signal: 'SIG-8911', correlation_score: 0.89, delta_seconds: 11 },
      { source_signal: 'SIG-8911', target_signal: 'SIG-8914', correlation_score: 0.82, delta_seconds: 8 },
    ],
    []
  );

  // Extract real live nodes and edges from graphData
  const liveNodesRaw = graphData?.nodes_data && graphData.nodes_data.length > 0
    ? graphData.nodes_data
    : graphData?.nodes && graphData.nodes.length > 0
    ? graphData.nodes.map((id, idx) => ({ id, service: (incident?.services || ['comms-service'])[idx % (incident?.services?.length || 1)] }))
    : fallbackNodes;

  const liveEdgesRaw = graphData?.edges && graphData.edges.length > 0
    ? graphData.edges
    : fallbackEdges;

  // Determine root cause node: matches root_cause_service or earliest timestamp
  const rootNodeId = useMemo(() => {
    if (!liveNodesRaw || liveNodesRaw.length === 0) return 'SIG-8902';
    if (incident?.root_cause_service) {
      const match = liveNodesRaw.find((n) =>
        (n.service && incident.root_cause_service.includes(n.service)) ||
        (n.component && incident.root_cause_service.includes(n.component))
      );
      if (match) return match.id;
    }
    return liveNodesRaw[0].id;
  }, [liveNodesRaw, incident]);

  // Compute topological coordinates for live nodes
  const layoutNodes = useMemo(() => {
    if (!liveNodesRaw || liveNodesRaw.length === 0) return [];

    const nodesList = [...liveNodesRaw];
    const root = nodesList.find((n) => n.id === rootNodeId) || nodesList[0];
    const nonRoot = nodesList.filter((n) => n.id !== root.id);

    // Mid layer vs end layer split
    const midCount = Math.ceil(nonRoot.length / 2);
    const midNodes = nonRoot.slice(0, midCount);
    const endNodes = nonRoot.slice(midCount);

    const result = [];

    // Root node at col 0
    result.push({
      ...root,
      x: 100,
      y: 220,
      role: 'ROOT CAUSE',
      badgeBg: '#D6A62C',
      badgeColor: '#FFFFFF',
    });

    // Mid layer nodes at col 1
    const midStartY = midNodes.length === 1 ? 220 : 120;
    const midStepY = midNodes.length > 1 ? 230 / (midNodes.length - 1 || 1) : 0;
    midNodes.forEach((node, i) => {
      result.push({
        ...node,
        x: 390,
        y: midStartY + i * midStepY,
        role: node.role || 'DOWNSTREAM',
        badgeBg: '#EAE6DB',
        badgeColor: '#3D4654',
      });
    });

    // End layer nodes at col 2
    const endStartY = endNodes.length === 1 ? 220 : 90;
    const endStepY = endNodes.length > 1 ? 250 / (endNodes.length - 1 || 1) : 0;
    endNodes.forEach((node, i) => {
      result.push({
        ...node,
        x: 670,
        y: endStartY + i * endStepY,
        role: node.role || (i % 2 === 0 ? 'SYMPTOM' : 'ISOLATION BOUNDARY'),
        badgeBg: i % 2 === 0 ? 'rgba(186, 26, 26, 0.1)' : '#3D4654',
        badgeColor: i % 2 === 0 ? '#BA1A1A' : '#FFFFFF',
      });
    });

    return result;
  }, [liveNodesRaw, rootNodeId]);

  // Active selected node
  const activeNode = useMemo(() => {
    if (!layoutNodes || layoutNodes.length === 0) return fallbackNodes[0];
    if (selectedNodeId) {
      const found = layoutNodes.find((n) => n.id === selectedNodeId);
      if (found) return found;
    }
    return layoutNodes[0];
  }, [layoutNodes, selectedNodeId]);

  // Compute edges with coordinates
  const layoutEdges = useMemo(() => {
    const nodeMap = new Map(layoutNodes.map((n) => [n.id, n]));
    const list = [];

    liveEdgesRaw.forEach((edge) => {
      const srcId = edge.source_signal || edge.source;
      const tgtId = edge.target_signal || edge.target;
      const src = nodeMap.get(srcId);
      const tgt = nodeMap.get(tgtId);

      if (src && tgt) {
        const isFromRoot = src.id === rootNodeId;
        const weight = edge.correlation_score || edge.weight || 0.88;
        const deltaSec = edge.delta_seconds || 14;

        // Curve start & end
        const x1 = src.x + 180;
        const y1 = src.y + 40;
        const x2 = tgt.x;
        const y2 = tgt.y + 40;
        const cx1 = x1 + (x2 - x1) * 0.45;
        const cy1 = y1;
        const cx2 = x1 + (x2 - x1) * 0.55;
        const cy2 = y2;
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;

        list.push({
          id: `${srcId}-${tgtId}`,
          d: `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`,
          midX,
          midY,
          weight: weight.toFixed(2),
          deltaSec,
          isFromRoot,
        });
      }
    });

    return list;
  }, [layoutNodes, liveEdgesRaw, rootNodeId]);

  const handleZoomIn = () => setZoomLevel((z) => Math.min(Number((z + 0.15).toFixed(2)), 1.8));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(Number((z - 0.15).toFixed(2)), 0.6));
  const handleFitView = () => setZoomLevel(1.0);
  const handleCenterCluster = () => {
    setZoomLevel(1.1);
    setSelectedNodeId(rootNodeId);
  };

  const handleExportTopology = () => {
    const exportData = {
      incident_id: incident?.id || 'INC-2ED8DD',
      modularity: 0.88,
      confidence: incident?.confidence || 0.982,
      nodes: layoutNodes,
      edges: liveEdgesRaw,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `topology-${incident?.id || 'INC-2ED8DD'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top View Control Bar */}
      <div
        className="glass-card"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 20px',
          borderRadius: 'var(--radius-xl)',
          background: '#FAF8F0',
          border: '1px solid var(--border-subtle)',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: '#D6A62C',
              display: 'inline-block',
            }}
          />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#252525' }}>
            Incident Correlation Topology
          </h2>
          <span
            style={{
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: '#EAE6DB',
              color: '#565F6E',
              fontWeight: 600,
            }}
          >
            {incident?.id || 'INC-2ED8DD'}
          </span>
          <span style={{ fontSize: '0.78rem', color: '#565F6E' }}>
            Graph modularity inference: active
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* View Toggles */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              background: '#EAE6DB',
              borderRadius: 'var(--radius-lg)',
              padding: '3px',
              fontSize: '0.78rem',
            }}
          >
            {[
              { id: 'topo', label: 'Topological View' },
              { id: 'time', label: 'Timeline Directed' },
              { id: 'latency', label: 'Show Latency Edges' },
            ].map((btn) => (
              <button
                key={btn.id}
                onClick={() => setViewMode(btn.id)}
                style={{
                  padding: '5px 12px',
                  borderRadius: 'var(--radius-md)',
                  background: viewMode === btn.id ? '#FAF8F0' : 'transparent',
                  color: viewMode === btn.id ? '#252525' : '#565F6E',
                  fontWeight: viewMode === btn.id ? 700 : 500,
                  boxShadow: viewMode === btn.id ? 'var(--shadow-sm)' : 'none',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                }}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {/* Zoom & Fit Controls */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
              background: '#EAE6DB',
              borderRadius: 'var(--radius-lg)',
              padding: '3px',
            }}
          >
            <button
              onClick={handleZoomIn}
              title="Zoom In"
              style={{
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-sm)',
                background: 'transparent',
                border: 'none',
                color: '#252525',
                cursor: 'pointer',
              }}
            >
              <ZoomIn size={15} />
            </button>
            <button
              onClick={handleZoomOut}
              title="Zoom Out"
              style={{
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-sm)',
                background: 'transparent',
                border: 'none',
                color: '#252525',
                cursor: 'pointer',
              }}
            >
              <ZoomOut size={15} />
            </button>
            <button
              onClick={handleFitView}
              title="Fit to View"
              style={{
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-sm)',
                background: 'transparent',
                border: 'none',
                color: '#252525',
                cursor: 'pointer',
              }}
            >
              <Maximize2 size={15} />
            </button>
            <button
              onClick={handleCenterCluster}
              title="Center Cluster"
              style={{
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-sm)',
                background: 'transparent',
                border: 'none',
                color: '#252525',
                cursor: 'pointer',
              }}
            >
              <Crosshair size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: DAG Graph (8 cols) + Right Stack (4 cols) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(12, 1fr)',
          gap: '20px',
          alignItems: 'start',
        }}
      >
        {/* Main Bento Card: Telemetry Causality DAG Graph (Spans 8 cols) */}
        <div
          className="glass-card"
          style={{
            gridColumn: 'span 8',
            borderRadius: 'var(--radius-xl)',
            background: '#FAF8F0',
            border: '1px solid var(--border-subtle)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
          }}
        >
          {/* Canvas Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 20px',
              background: '#FAF8F0',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Network size={18} color="#D6A62C" />
              <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#252525' }}>
                Telemetry Causality DAG
              </span>
              <span
                style={{
                  fontSize: '0.7rem',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  background: '#EAE6DB',
                  color: '#565F6E',
                }}
              >
                {layoutNodes.length} Nodes &bull; {layoutEdges.length} Propagation Edges
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.74rem', color: '#565F6E' }}>
                Autonomous Resolution Confidence
              </span>
              <span
                style={{
                  fontSize: '0.74rem',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FEDD7A',
                  color: '#776001',
                  fontWeight: 700,
                  border: '1px solid #D6A62C',
                }}
              >
                {incident?.confidence ? `${(incident.confidence * 100).toFixed(1)}%` : '98.2%'}
              </span>
            </div>
          </div>

          {/* SVG Canvas Container */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '580px',
              background: '#1C232D',
              overflow: 'hidden',
              userSelect: 'none',
            }}
          >
            {/* Grid Dots Overlay */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                opacity: 0.25,
                pointerEvents: 'none',
                backgroundImage: 'radial-gradient(#DAE3F5 1px, transparent 1px)',
                backgroundSize: '24px 24px',
              }}
            />

            <svg
              viewBox="0 0 940 580"
              style={{
                width: '100%',
                height: '100%',
                transform: `scale(${zoomLevel})`,
                transformOrigin: 'center center',
                transition: 'transform 0.25s ease-out',
                cursor: 'grab',
              }}
            >
              <defs>
                <filter id="node-shadow" x="-10%" y="-10%" width="120%" height="120%">
                  <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#000000" floodOpacity="0.35" />
                </filter>
                <filter id="root-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="0" stdDeviation="12" floodColor="#D6A62C" floodOpacity="0.65" />
                </filter>
                <marker id="arrow-solid" markerWidth="6" markerHeight="6" refX="7" refY="5" viewBox="0 0 10 10" orient="auto-start-reverse">
                  <path d="M 0 1 L 9 5 L 0 9 z" fill="#A5AEBE" />
                </marker>
                <marker id="arrow-causal" markerWidth="6" markerHeight="6" refX="7" refY="5" viewBox="0 0 10 10" orient="auto-start-reverse">
                  <path d="M 0 1 L 9 5 L 0 9 z" fill="#F2BF44" />
                </marker>
              </defs>

              {/* Cluster Boundary Box */}
              <rect
                x="60"
                y="45"
                width="820"
                height="480"
                rx="24"
                fill="#252E3B"
                fillOpacity="0.55"
                stroke="#D6A62C"
                strokeWidth="1.5"
                strokeDasharray="6 6"
              />
              <g transform="translate(80, 70)">
                <rect x="0" y="0" width="380" height="24" rx="12" fill="#FEDD7A" fillOpacity="0.2" stroke="#D6A62C" strokeWidth="1" />
                <text x="12" y="16" fill="#FEDD7A" fontFamily="Inter" fontSize="10.5" fontWeight="600" letterSpacing="0.04em">
                  INCIDENT CLUSTER BOUNDARY &bull; MODULARITY 0.88 &bull; CONF {incident?.confidence ? `${Math.round(incident.confidence * 100)}%` : '98%'}
                </text>
              </g>

              {/* Dynamic SVG Edges */}
              {layoutEdges.map((edge) => (
                <g key={edge.id} className="graph-edge">
                  <path
                    d={edge.d}
                    fill="none"
                    stroke={edge.isFromRoot ? '#F2BF44' : '#A5AEBE'}
                    strokeWidth={edge.isFromRoot ? '2.5' : '1.75'}
                    strokeDasharray={edge.isFromRoot ? '4 3' : 'none'}
                    markerEnd={edge.isFromRoot ? 'url(#arrow-causal)' : 'url(#arrow-solid)'}
                  />
                  <rect
                    x={edge.midX - 50}
                    y={edge.midY - 10}
                    width="100"
                    height="20"
                    rx="10"
                    fill="#131C29"
                    stroke={edge.isFromRoot ? '#785A00' : '#3E4755'}
                    strokeWidth="1"
                  />
                  <text
                    x={edge.midX}
                    y={edge.midY + 4}
                    textAnchor="middle"
                    fill={edge.isFromRoot ? '#FEDD7A' : '#DAE3F5'}
                    fontFamily="Inter"
                    fontSize="9.5"
                    fontWeight={edge.isFromRoot ? '600' : '500'}
                  >
                    dt: +{edge.deltaSec}s, {edge.weight}
                  </text>
                </g>
              ))}

              {/* Dynamic SVG Nodes */}
              {layoutNodes.map((node) => {
                const isSelected = activeNode.id === node.id;
                const isRoot = node.role === 'ROOT CAUSE';

                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    onClick={() => setSelectedNodeId(node.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Node Card Background */}
                    <rect
                      x="0"
                      y="0"
                      width={isRoot ? '230' : '200'}
                      height={isRoot ? '90' : '84'}
                      rx="16"
                      fill={isRoot ? '#131C29' : '#252E3B'}
                      filter={isRoot ? 'url(#root-glow)' : 'url(#node-shadow)'}
                      stroke={isSelected ? '#D6A62C' : isRoot ? '#D6A62C' : '#3E4755'}
                      strokeWidth={isSelected || isRoot ? '2.5' : '1.5'}
                    />

                    {/* Role Header Badge */}
                    <rect
                      x="12"
                      y={isRoot ? '-12' : '-10'}
                      width={isRoot ? '140' : '100'}
                      height={isRoot ? '20' : '18'}
                      rx={isRoot ? '10' : '9'}
                      fill={isRoot ? '#D6A62C' : node.role === 'SYMPTOM' ? '#BA1A1A' : '#39424F'}
                    />
                    <text
                      x={isRoot ? '82' : '62'}
                      y={isRoot ? '1.5' : '2.5'}
                      textAnchor="middle"
                      fill={isRoot ? '#251A00' : '#FFFFFF'}
                      fontFamily="Inter"
                      fontSize={isRoot ? '10' : '9'}
                      fontWeight="700"
                      letterSpacing="0.04em"
                    >
                      {node.role}
                    </text>

                    {/* Node Icon Circle */}
                    <circle
                      cx="26"
                      cy="36"
                      r="13"
                      fill={isRoot ? 'rgba(214, 166, 44, 0.25)' : 'rgba(218, 227, 245, 0.15)'}
                    />
                    <circle
                      cx="26"
                      cy="36"
                      r="6"
                      fill={isRoot ? '#F2BF44' : node.role === 'SYMPTOM' ? '#BA1A1A' : '#BEC7D8'}
                    />

                    {/* Node Text Content */}
                    <text
                      x="46"
                      y="33"
                      fill="#FFFFFF"
                      fontFamily="Manrope, Inter"
                      fontSize="12.5"
                      fontWeight="700"
                    >
                      {node.id}
                    </text>
                    <text
                      x="46"
                      y="47"
                      fill="#BEC7D8"
                      fontFamily="Inter"
                      fontSize="10"
                    >
                      {node.service}:{node.component || 'core'}
                    </text>
                    <text
                      x="14"
                      y="70"
                      fill={isRoot ? '#FEDD7A' : '#EBE8DF'}
                      fontFamily="Inter"
                      fontSize="10.5"
                      fontWeight={isRoot ? '600' : '500'}
                    >
                      {(node.anomaly_type || node.message || 'Signal Anomaly').slice(0, 24)}
                    </text>

                    {/* Status Dot */}
                    <circle
                      cx={isRoot ? '210' : '184'}
                      cy="32"
                      r="3.5"
                      fill={isRoot || node.role === 'SYMPTOM' ? '#BA1A1A' : '#D6A62C'}
                    />
                  </g>
                );
              })}
            </svg>

            {/* Floating Topology Legend (Bottom Left) */}
            <div
              style={{
                position: 'absolute',
                bottom: '16px',
                left: '16px',
                padding: '12px 16px',
                borderRadius: 'var(--radius-lg)',
                background: 'rgba(19, 28, 41, 0.9)',
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(86, 95, 110, 0.4)',
                pointerEvents: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: '#DAE3F5',
                }}
              >
                Topology Graph Legend
              </span>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: '8px 16px',
                  fontSize: '0.74rem',
                  color: '#FFFFFF',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#D6A62C' }} />
                  <span>Root Cause Origin</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#DAE3F5' }} />
                  <span>Correlated Signal</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '14px', height: '2px', borderTop: '2px dashed #F2BF44' }} />
                  <span>Causal Propagation</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '14px', height: '2px', background: '#BEC7D8' }} />
                  <span>Topological Dependency</span>
                </div>
              </div>
            </div>

            {/* Floating Live Indicator (Top Right) */}
            <div
              style={{
                position: 'absolute',
                top: '16px',
                right: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 12px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(19, 28, 41, 0.9)',
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(86, 95, 110, 0.4)',
                fontSize: '0.72rem',
                color: '#FFFFFF',
              }}
            >
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#D6A62C' }} />
              <span style={{ fontWeight: 500 }}>Live Causal Inference Stream</span>
            </div>
          </div>
        </div>

        {/* Right Stack: 2 interlocking Bento Cards (Spans 4 cols) */}
        <div style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Bento Card 1: Incident Metadata Card */}
          <div
            className="glass-card"
            style={{
              padding: '20px 22px',
              borderRadius: 'var(--radius-xl)',
              background: '#FAF8F0',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingBottom: '10px',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: 'var(--radius-md)',
                    background: '#3D4654',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#D6A62C',
                  }}
                >
                  <Info size={15} />
                </div>
                <span style={{ fontSize: '0.94rem', fontWeight: 700, color: '#252525' }}>
                  Incident Metadata
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  background: '#FEDD7A',
                  color: '#776001',
                  border: '1px solid #D6A62C',
                }}
              >
                ACTIVE ROOT
              </span>
            </div>

            {/* Grid of Key-Values */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '10px 12px',
                padding: '14px 16px',
                borderRadius: 'var(--radius-lg)',
                background: '#F4F1E8',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Incident ID</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#252525' }}>
                  {incident?.id || 'INC-2ED8DD'}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Severity Metric</span>
                <span style={{ fontWeight: 700, color: '#BA1A1A' }}>
                  {(incident?.severity || 52.8).toFixed(1)} / 100 (HIGH)
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', paddingTop: '4px' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Confidence</span>
                <span style={{ fontWeight: 700, color: '#785A00' }}>
                  {incident?.confidence ? `${Math.round(incident.confidence * 100)}%` : '98%'} DETERMINISTIC
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', paddingTop: '4px' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Environment</span>
                <span style={{ color: '#252525' }}>
                  {incident?.environment?.toUpperCase() || 'PROD'} (eu-west-1)
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', paddingTop: '4px' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Primary Service</span>
                <span style={{ color: '#252525' }}>
                  {(incident?.services || ['comms-service'])[0]}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', paddingTop: '4px' }}>
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Correlated Signals</span>
                <span style={{ color: '#252525' }}>
                  {layoutNodes.length} signals
                </span>
              </div>
              <div
                style={{
                  gridColumn: 'span 2',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingTop: '8px',
                  borderTop: '1px solid var(--border-subtle)',
                  marginTop: '4px',
                }}
              >
                <span style={{ color: '#565F6E', fontSize: '0.68rem', textTransform: 'uppercase' }}>Noise Reduction Ratio</span>
                <span style={{ fontWeight: 700, color: '#3D4654' }}>99.4% Compression</span>
              </div>
            </div>
          </div>

          {/* Bento Card 2: Selected Node Details & Action Hub */}
          <div
            className="glass-card"
            style={{
              padding: '20px 22px',
              borderRadius: 'var(--radius-xl)',
              background: '#FAF8F0',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingBottom: '10px',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: 'var(--radius-md)',
                    background: '#3D4654',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#D6A62C',
                  }}
                >
                  <Database size={15} />
                </div>
                <span style={{ fontSize: '0.94rem', fontWeight: 700, color: '#252525' }}>
                  Selected Node Details
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  background: activeNode.badgeBg || '#D6A62C',
                  color: activeNode.badgeColor || '#FFFFFF',
                }}
              >
                {activeNode.role || 'NODE'}
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {/* Node Identifier Box */}
              <div
                style={{
                  padding: '12px 14px',
                  borderRadius: 'var(--radius-lg)',
                  background: '#F4F1E8',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '3px',
                }}
              >
                <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#807663', textTransform: 'uppercase' }}>
                  Signal Identifier
                </span>
                <span style={{ fontSize: '0.94rem', fontWeight: 700, color: '#252525' }}>
                  {activeNode.id} ({activeNode.role || 'Correlated Node'})
                </span>
                <span style={{ fontSize: '0.74rem', color: '#565F6E' }}>
                  {activeNode.service}:{activeNode.component || 'core'}
                </span>
              </div>

              {/* Attributes List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.74rem' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    background: '#F4F1E8',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <span style={{ color: '#565F6E' }}>First Detected:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#252525' }}>
                    {activeNode.timestamp
                      ? new Date(activeNode.timestamp).toLocaleTimeString() + ' UTC'
                      : '14:22:04.112 UTC'}
                  </span>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    background: '#F4F1E8',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <span style={{ color: '#565F6E' }}>Signal Vector:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#252525' }}>
                    {activeNode.anomaly_type || 'ResourceStarvation::PoolExhaustion'}
                  </span>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    background: '#F4F1E8',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <span style={{ color: '#565F6E' }}>Telemetry Source:</span>
                  <span style={{ color: '#252525', fontWeight: 500 }}>
                    {activeNode.source || 'Datadog / Prometheus Redis Exporter'}
                  </span>
                </div>
              </div>

              {/* Diagnostic Synthesis */}
              <div
                style={{
                  padding: '12px 14px',
                  borderRadius: 'var(--radius-lg)',
                  background: '#F4F1E8',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#3D4654' }}>
                  Diagnostic Synthesis
                </span>
                <p style={{ fontSize: '0.76rem', color: '#252525', lineHeight: 1.45 }}>
                  {activeNode.message ||
                    activeNode.notes ||
                    'Correlated causal anomaly identified in evidence graph topological analysis.'}
                </p>
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingTop: '4px' }}>
              <button
                className="btn btn-primary"
                onClick={() => onNavigate && onNavigate('review')}
                style={{
                  width: '100%',
                  padding: '10px 16px',
                  borderRadius: 'var(--radius-lg)',
                  fontSize: '0.84rem',
                  background: '#D6A62C',
                  color: '#FFFFFF',
                }}
              >
                <span>Proceed to Ticket Draft Review</span>
                <ArrowRight size={15} />
              </button>

              <button
                className="btn btn-secondary"
                onClick={handleExportTopology}
                style={{
                  width: '100%',
                  padding: '9px 16px',
                  borderRadius: 'var(--radius-lg)',
                  fontSize: '0.82rem',
                  background: '#FAF8F0',
                  borderColor: 'rgba(61, 70, 84, 0.25)',
                  color: '#252525',
                }}
              >
                <Download size={14} color="#565F6E" />
                <span>Export Topology JSON</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
