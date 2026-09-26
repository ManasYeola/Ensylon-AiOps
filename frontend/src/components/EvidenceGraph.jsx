import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  Network,
  Info,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  ChevronRight,
} from 'lucide-react';
import { formatIST } from '../utils/time';

// Service color scheme for distinct visual clustering matching broadsheet palette
const SERVICE_COLORS = {
  payment: { fill: '#3D4654', stroke: '#2A313C', label: 'Payments' },
  carrier: { fill: '#2563EB', stroke: '#1D4ED8', label: 'Carrier' },
  enrollment: { fill: '#0D9488', stroke: '#0F766E', label: 'Enrollment' },
  comms: { fill: '#8B5CF6', stroke: '#7C3AED', label: 'Comms' },
  order: { fill: '#7C3AED', stroke: '#6D28D9', label: 'Order Worker' },
  docforge: { fill: '#10B981', stroke: '#059669', label: 'DocForge' },
  rulesforge: { fill: '#D97706', stroke: '#B45309', label: 'RulesForge' },
  agency: { fill: '#DC2626', stroke: '#B91C1C', label: 'Agency Gateway' },
  default: { fill: '#565F6E', stroke: '#3D4654', label: 'Core Service' },
};

// Distinct warm amber/gold for Strong Edges matching broadsheet theme
const STRONG_EDGE = {
  stroke: '#D6A62C',
  highlight: '#B8860B',
  glow: 'rgba(214, 166, 44, 0.4)',
  badgeBg: '#FAF8F0',
  label: 'Strong Correlation Edge',
};

function getServiceColor(serviceName = '') {
  const s = String(serviceName).toLowerCase();
  if (s.includes('payment')) return SERVICE_COLORS.payment;
  if (s.includes('carrier')) return SERVICE_COLORS.carrier;
  if (s.includes('enrollment')) return SERVICE_COLORS.enrollment;
  if (s.includes('comms')) return SERVICE_COLORS.comms;
  if (s.includes('order')) return SERVICE_COLORS.order;
  if (s.includes('docforge')) return SERVICE_COLORS.docforge;
  if (s.includes('rulesforge')) return SERVICE_COLORS.rulesforge;
  if (s.includes('agency')) return SERVICE_COLORS.agency;
  return SERVICE_COLORS.default;
}

export default function EvidenceGraph({ incident, graphData }) {
  const canvasRef = useRef(null);

  // View Controls (Cutoff removed as requested)
  const [viewMode, setViewMode] = useState('backbone'); // 'backbone' (MST), 'top2', 'all'
  const [weightMode, setWeightMode] = useState('focus'); // 'focus' (hover/select only), 'all'
  const [searchQuery, setSearchQuery] = useState('');

  // Selected & Hovered State
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [hoveredNodeId, setHoveredNodeId] = useState(null);
  const [hoverPosition, setHoverPosition] = useState(null);

  // Pan and Zoom Transform: { x: 0, y: 0, k: 1 }
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const isDraggingCanvasRef = useRef(false);
  const draggedNodeRef = useRef(null);
  const dragStartRef = useRef({ x: 0, y: 0 });

  // Node positions are stored and fixed after stabilization
  const nodesRef = useRef([]);
  const edgesRef = useRef([]);

  // Normalize raw nodes and edges
  const { rawNodes, rawEdges, nodeIndexMap } = useMemo(() => {
    if (!graphData || !graphData.nodes) {
      return { rawNodes: [], rawEdges: [], nodeIndexMap: new Map() };
    }

    const nodes = (graphData.nodes_data || graphData.nodes.map((id) => ({ id }))).map((n, idx) => ({
      ...n,
      id: String(n.id || n.signal_id || `node-${idx}`),
      shortIdx: idx + 1,
      shortId: (n.id || '').length > 10 ? `...${(n.id || '').slice(-6)}` : n.id,
      color: getServiceColor(n.service),
    }));

    const indexMap = new Map();
    nodes.forEach((n) => indexMap.set(n.id, n));

    const edges = (graphData.edges || []).map((e) => {
      const score =
        typeof e.weight === 'number'
          ? e.weight
          : typeof e.correlation_score === 'number'
          ? e.correlation_score
          : 0;
      return {
        ...e,
        weight: score,
        correlation_score: score,
      };
    });

    return { rawNodes: nodes, rawEdges: edges, nodeIndexMap: indexMap };
  }, [graphData]);

  // Compute Active Edges based on View Mode (automatic strong threshold 0.70)
  const activeEdges = useMemo(() => {
    const valid = rawEdges.filter((e) => e.weight >= 0.70);

    if (viewMode === 'all') return valid.length > 0 ? valid : rawEdges;

    if (viewMode === 'top2') {
      const nodeEdges = new Map();
      rawEdges.forEach((e) => {
        if (!nodeEdges.has(e.source_signal)) nodeEdges.set(e.source_signal, []);
        if (!nodeEdges.has(e.target_signal)) nodeEdges.set(e.target_signal, []);
        nodeEdges.get(e.source_signal).push(e);
        nodeEdges.get(e.target_signal).push(e);
      });

      const chosen = new Set();
      const result = [];
      nodeEdges.forEach((edgesList) => {
        const sorted = [...edgesList].sort((a, b) => b.weight - a.weight).slice(0, 2);
        sorted.forEach((e) => {
          const key = [e.source_signal, e.target_signal].sort().join('--');
          if (!chosen.has(key)) {
            chosen.add(key);
            result.push(e);
          }
        });
      });
      return result;
    }

    // Default: 'backbone' (Maximum Spanning Tree of correlation weights)
    const sorted = [...rawEdges].sort((a, b) => b.weight - a.weight);
    const parent = new Map();
    const find = (i) => {
      if (!parent.has(i)) parent.set(i, i);
      if (parent.get(i) === i) return i;
      const root = find(parent.get(i));
      parent.set(i, root);
      return root;
    };
    const union = (i, j) => {
      const rootI = find(i);
      const rootJ = find(j);
      if (rootI !== rootJ) {
        parent.set(rootI, rootJ);
        return true;
      }
      return false;
    };

    const mstEdges = [];
    const mstSet = new Set();

    for (const edge of sorted) {
      if (union(edge.source_signal, edge.target_signal)) {
        mstEdges.push(edge);
        const key = [edge.source_signal, edge.target_signal].sort().join('--');
        mstSet.add(key);
      }
    }

    // Add secondary top cross-links if high confidence
    const nodeDegree = new Map();
    mstEdges.forEach((e) => {
      nodeDegree.set(e.source_signal, (nodeDegree.get(e.source_signal) || 0) + 1);
      nodeDegree.set(e.target_signal, (nodeDegree.get(e.target_signal) || 0) + 1);
    });

    for (const edge of sorted) {
      const key = [edge.source_signal, edge.target_signal].sort().join('--');
      if (!mstSet.has(key)) {
        const degA = nodeDegree.get(edge.source_signal) || 0;
        const degB = nodeDegree.get(edge.target_signal) || 0;
        if (degA < 3 && degB < 3 && edge.weight >= 0.82) {
          mstEdges.push(edge);
          mstSet.add(key);
          nodeDegree.set(edge.source_signal, degA + 1);
          nodeDegree.set(edge.target_signal, degB + 1);
        }
      }
    }

    return mstEdges;
  }, [rawEdges, viewMode]);

  // STABLE LAYOUT: Compute force simulation once and FREEZE positions (no continuous movement)
  const stabilizeLayout = useCallback(() => {
    if (rawNodes.length === 0) return;

    const canvas = canvasRef.current;
    const width = canvas?.clientWidth || 700;
    const height = canvas?.clientHeight || 450;
    const centerX = width / 2;
    const centerY = height / 2;

    // Cluster nodes by service initially
    const serviceClusters = new Map();
    rawNodes.forEach((n) => {
      const svc = n.service || 'default';
      if (!serviceClusters.has(svc)) serviceClusters.set(svc, []);
      serviceClusters.get(svc).push(n);
    });

    const clusterCount = serviceClusters.size;
    const clusterAngleStep = (2 * Math.PI) / Math.max(clusterCount, 1);
    const clusterRadius = Math.min(width, height) * 0.35;

    const nodes = [];
    let clusterIdx = 0;

    serviceClusters.forEach((clusterNodes) => {
      const clusterAngle = clusterIdx * clusterAngleStep;
      const cX = centerX + (clusterCount > 1 ? clusterRadius * Math.cos(clusterAngle) : 0);
      const cY = centerY + (clusterCount > 1 ? clusterRadius * Math.sin(clusterAngle) : 0);
      const subRadius = Math.min(width, height) * 0.16;

      clusterNodes.forEach((node, i) => {
        const subAngle = (i / Math.max(clusterNodes.length, 1)) * 2 * Math.PI;
        nodes.push({
          ...node,
          x: cX + (clusterNodes.length > 1 ? subRadius * Math.cos(subAngle) : 0) + (Math.random() - 0.5) * 15,
          y: cY + (clusterNodes.length > 1 ? subRadius * Math.sin(subAngle) : 0) + (Math.random() - 0.5) * 15,
          vx: 0,
          vy: 0,
          radius: 15,
        });
      });
      clusterIdx++;
    });

    const edges = activeEdges;

    // Run 150 simulation iterations with cooling decay to reach a rock-solid, static state
    const iterations = 150;
    for (let step = 0; step < iterations; step++) {
      const alpha = Math.max(0.02, 1 - step / iterations);

      // Repulsion between nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const minDist = 80;
          if (dist < minDist) {
            const force = ((minDist - dist) / dist) * 0.15 * alpha;
            nodes[i].vx -= dx * force;
            nodes[i].vy -= dy * force;
            nodes[j].vx += dx * force;
            nodes[j].vy += dy * force;
          }
        }
      }

      // Spring attraction along active edges
      edges.forEach((edge) => {
        const source = nodes.find((n) => n.id === edge.source_signal);
        const target = nodes.find((n) => n.id === edge.target_signal);
        if (source && target) {
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const targetDist = 100 * (1 - edge.weight * 0.3);
          const force = (dist - targetDist) * 0.01 * edge.weight * alpha;
          source.vx += (dx / dist) * force;
          source.vy += (dy / dist) * force;
          target.vx -= (dx / dist) * force;
          target.vy -= (dy / dist) * force;
        }
      });

      // Centering gravity & damping
      nodes.forEach((node) => {
        node.vx += (centerX - node.x) * 0.004 * alpha;
        node.vy += (centerY - node.y) * 0.004 * alpha;
        node.vx *= 0.75;
        node.vy *= 0.75;
        node.x += node.vx;
        node.y += node.vy;

        // Keep inside bounds
        node.x = Math.max(40, Math.min(width - 40, node.x));
        node.y = Math.max(40, Math.min(height - 40, node.y));
      });
    }

    // Simulation is completely finished - velocities reset to 0
    nodes.forEach((n) => {
      n.vx = 0;
      n.vy = 0;
    });

    nodesRef.current = nodes;
    edgesRef.current = edges;

    if (!selectedNodeId && nodes.length > 0) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [rawNodes, activeEdges, selectedNodeId]);

  // Run stabilization when rawNodes or viewMode changes
  useEffect(() => {
    stabilizeLayout();
  }, [stabilizeLayout]);

  // Static Render Function (Draws the frozen layout - ZERO continuous animation)
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const width = canvas.clientWidth || 700;
    const height = canvas.clientHeight || 450;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const nodes = nodesRef.current;
    const edges = edgesRef.current;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    ctx.save();
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // Subtle background grid matching warm broadsheet cream
    const worldLeft = -transform.x / transform.k - 200;
    const worldTop = -transform.y / transform.k - 200;
    const worldRight = (width - transform.x) / transform.k + 200;
    const worldBottom = (height - transform.y) / transform.k + 200;

    ctx.fillStyle = 'rgba(61, 70, 84, 0.12)';
    const step = 40;
    const startX = Math.floor(worldLeft / step) * step;
    const startY = Math.floor(worldTop / step) * step;
    for (let x = startX; x < worldRight; x += step) {
      for (let y = startY; y < worldBottom; y += step) {
        ctx.beginPath();
        ctx.arc(x, y, 1, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 1. Draw Edges using broadsheet gold (#D6A62C)
    edges.forEach((edge) => {
      const source = nodes.find((n) => n.id === edge.source_signal);
      const target = nodes.find((n) => n.id === edge.target_signal);
      if (!source || !target || isNaN(source.x) || isNaN(target.x)) return;

      const isConnectedToSelected =
        selectedNodeId && (selectedNodeId === source.id || selectedNodeId === target.id);
      const isConnectedToHovered =
        hoveredNodeId && (hoveredNodeId === source.id || hoveredNodeId === target.id);
      const isHighlighted = isConnectedToSelected || isConnectedToHovered;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);

      if (isHighlighted) {
        // Glowing gold for active / focused edge
        ctx.strokeStyle = '#D6A62C';
        ctx.lineWidth = 2.8;
        ctx.shadowColor = 'rgba(214, 166, 44, 0.45)';
        ctx.shadowBlur = 10;
      } else if (selectedNodeId || hoveredNodeId) {
        // Dimmed edges when focusing on a specific node
        ctx.strokeStyle = 'rgba(61, 70, 84, 0.08)';
        ctx.lineWidth = 1;
        ctx.shadowBlur = 0;
      } else {
        // Crisp Edge in gold color
        ctx.strokeStyle = 'rgba(214, 166, 44, 0.65)';
        ctx.lineWidth = 1.6;
        ctx.shadowBlur = 0;
      }

      ctx.stroke();
      ctx.shadowBlur = 0;

      // Draw Weight Badge (Only when highlighted OR if weightMode is 'all')
      const shouldDrawBadge = isHighlighted || (weightMode === 'all' && edges.length <= 40);
      if (shouldDrawBadge) {
        const midX = (source.x + target.x) / 2;
        const midY = (source.y + target.y) / 2;
        const label = edge.weight.toFixed(2);

        ctx.font = '700 10px JetBrains Mono, monospace';
        const metrics = ctx.measureText(label);
        const badgeW = metrics.width + 10;
        const badgeH = 16;

        ctx.fillStyle = isHighlighted ? '#D6A62C' : '#FAF8F0';
        ctx.strokeStyle = isHighlighted ? '#B8860B' : 'rgba(61, 70, 84, 0.25)';
        ctx.lineWidth = 1.2;

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH, 4);
        } else {
          ctx.rect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isHighlighted ? '#FFFFFF' : '#252525';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, midX, midY);
      }
    });

    // 2. Draw Nodes
    nodes.forEach((node) => {
      const isSelected = selectedNodeId === node.id;
      const isHovered = hoveredNodeId === node.id;
      const color = node.color || SERVICE_COLORS.default;

      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);

      // Fill circle
      ctx.fillStyle = isSelected ? '#D6A62C' : isHovered ? color.stroke : color.fill;
      ctx.fill();

      // Stroke & Glow
      ctx.strokeStyle = isSelected ? '#FFFFFF' : isHovered ? '#FFFFFF' : color.stroke;
      ctx.lineWidth = isSelected ? 3.5 : isHovered ? 2.5 : 1.5;
      if (isSelected || isHovered) {
        ctx.shadowColor = 'rgba(214, 166, 44, 0.45)';
        ctx.shadowBlur = 12;
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Clean Number Inside Circle
      ctx.fillStyle = '#FFFFFF';
      ctx.font = '700 10px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${node.shortIdx}`, node.x, node.y);

      // Label beneath node for selected, hovered, or search-matched
      const isSearched = searchQuery && node.id.toLowerCase().includes(searchQuery.toLowerCase());
      if (isSelected || isHovered || isSearched) {
        ctx.font = '600 10px JetBrains Mono, monospace';
        const labelText = `${node.service || 'signal'} (${node.shortId})`;
        const labelMetrics = ctx.measureText(labelText);
        const lw = labelMetrics.width + 12;
        const lh = 18;
        const ly = node.y + node.radius + 12;

        ctx.fillStyle = '#FAF8F0';
        ctx.strokeStyle = isSelected ? '#D6A62C' : 'rgba(61, 70, 84, 0.25)';
        ctx.lineWidth = 1;

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(node.x - lw / 2, ly - lh / 2, lw, lh, 4);
        } else {
          ctx.rect(node.x - lw / 2, ly - lh / 2, lw, lh);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? '#785A00' : '#252525';
        ctx.fillText(labelText, node.x, ly);
      }
    });

    ctx.restore();
  }, [transform, selectedNodeId, hoveredNodeId, weightMode, searchQuery]);

  // Redraw when transform, selection, hover, or mode changes
  useEffect(() => {
    drawCanvas();
  }, [drawCanvas]);

  // Convert mouse screen coordinates to world coordinates
  const getWorldCoords = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    return {
      x: (screenX - transform.x) / transform.k,
      y: (screenY - transform.y) / transform.k,
      screenX,
      screenY,
    };
  };

  // Canvas Mouse Events: Pan Canvas or Drag Node
  const handleMouseDown = (e) => {
    const { x, y } = getWorldCoords(e);
    const clickedNode = nodesRef.current.find((n) => {
      const dx = n.x - x;
      const dy = n.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= n.radius + 6;
    });

    if (clickedNode) {
      setSelectedNodeId(clickedNode.id);
      draggedNodeRef.current = clickedNode;
      dragStartRef.current = { x: x - clickedNode.x, y: y - clickedNode.y };
    } else {
      isDraggingCanvasRef.current = true;
      dragStartRef.current = { x: e.clientX - transform.x, y: e.clientY - transform.y };
    }
  };

  const handleMouseMove = (e) => {
    if (draggedNodeRef.current) {
      const { x, y } = getWorldCoords(e);
      draggedNodeRef.current.x = x - dragStartRef.current.x;
      draggedNodeRef.current.y = y - dragStartRef.current.y;
      drawCanvas();
      return;
    }

    if (isDraggingCanvasRef.current) {
      setTransform((prev) => ({
        ...prev,
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      }));
      return;
    }

    const { x, y, screenX, screenY } = getWorldCoords(e);
    const hovered = nodesRef.current.find((n) => {
      const dx = n.x - x;
      const dy = n.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= n.radius + 6;
    });

    if (hovered) {
      setHoveredNodeId(hovered.id);
      setHoverPosition({ x: screenX, y: screenY, node: hovered });
      if (canvasRef.current) canvasRef.current.style.cursor = 'pointer';
    } else {
      setHoveredNodeId(null);
      setHoverPosition(null);
      if (canvasRef.current) canvasRef.current.style.cursor = 'default';
    }
  };

  const handleMouseUp = () => {
    isDraggingCanvasRef.current = false;
    draggedNodeRef.current = null;
  };

  // Zoom with mouse wheel
  const handleWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.88;
    setTransform((prev) => {
      const nextK = Math.max(0.4, Math.min(3.0, prev.k * factor));
      return { ...prev, k: nextK };
    });
  };

  // Zoom & Reset Handlers
  const handleZoomIn = () => setTransform((prev) => ({ ...prev, k: Math.min(3.0, prev.k * 1.25) }));
  const handleZoomOut = () => setTransform((prev) => ({ ...prev, k: Math.max(0.4, prev.k * 0.8) }));
  const handleResetView = () => {
    setTransform({ x: 0, y: 0, k: 1 });
    stabilizeLayout();
  };

  // Selected Node Details
  const selectedNode = useMemo(() => {
    return nodeIndexMap.get(selectedNodeId) || nodesRef.current[0] || null;
  }, [selectedNodeId, nodeIndexMap]);

  // Connected Edges for Selected Node
  const selectedNodeEdges = useMemo(() => {
    if (!selectedNode) return [];
    return activeEdges
      .filter((e) => e.source_signal === selectedNode.id || e.target_signal === selectedNode.id)
      .map((e) => {
        const targetId = e.source_signal === selectedNode.id ? e.target_signal : e.source_signal;
        const targetNode = nodeIndexMap.get(targetId);
        return {
          ...e,
          targetId,
          targetNode,
        };
      })
      .sort((a, b) => b.weight - a.weight);
  }, [selectedNode, activeEdges, nodeIndexMap]);

  // Search filtered node list
  const filteredNodesList = useMemo(() => {
    if (!searchQuery) return rawNodes;
    const q = searchQuery.toLowerCase();
    return rawNodes.filter(
      (n) =>
        n.id.toLowerCase().includes(q) ||
        (n.service && n.service.toLowerCase().includes(q)) ||
        (n.component && n.component.toLowerCase().includes(q))
    );
  }, [rawNodes, searchQuery]);

  if (!graphData) {
    return (
      <div className="glass-card" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-secondary)', borderRadius: 'var(--radius-xl)' }}>
        <Network size={36} color="var(--cyan)" style={{ margin: '0 auto 16px', display: 'block', opacity: 0.8 }} />
        <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>Loading Evidence Graph...</h4>
        <p style={{ fontSize: '0.82rem', marginTop: '6px' }}>Fetching correlated signal nodes and dimensional edges</p>
      </div>
    );
  }

  if (!graphData.nodes || graphData.nodes.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-secondary)', borderRadius: 'var(--radius-xl)' }}>
        <Network size={36} color="var(--text-muted)" style={{ margin: '0 auto 16px', display: 'block' }} />
        <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>No Signal Nodes in Cluster</h4>
        <p style={{ fontSize: '0.82rem', marginTop: '6px' }}>This incident does not contain active anomalous signal nodes.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '16px' }}>
      {/* Canvas Viewport */}
      <div className="glass-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', borderRadius: 'var(--radius-xl)' }}>
        {/* Clean Controls Toolbar (Cutoff removed) */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            marginBottom: '12px',
            paddingBottom: '12px',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          {/* Header Title & Counts */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Network size={18} color={STRONG_EDGE.stroke} />
            <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Evidence Graph
            </h4>
            <span className="badge badge-amber font-mono" style={{ fontSize: '0.72rem' }}>
              {rawNodes.length} Nodes
            </span>
            <span
              className="badge badge-amber font-mono"
              style={{ fontSize: '0.72rem' }}
            >
              {activeEdges.length} Strong Edges
            </span>
          </div>
        </div>

        {/* Stable Static Canvas Viewport */}
        <div style={{ flex: 1, minHeight: '440px', position: 'relative', overflow: 'hidden', borderRadius: 'var(--radius-lg)' }}>
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
            style={{
              width: '100%',
              height: '100%',
              display: 'block',
              borderRadius: 'var(--radius-lg)',
              background: '#FAF8F0',
              border: '1px solid var(--border-subtle)',
            }}
          />

          {/* Hover Tooltip */}
          {hoverPosition && hoverPosition.node && (
            <div
              style={{
                position: 'absolute',
                left: `${Math.min(hoverPosition.x + 14, 520)}px`,
                top: `${Math.min(hoverPosition.y + 14, 380)}px`,
                pointerEvents: 'none',
                background: '#FAF8F0',
                border: '1px solid var(--border-medium)',
                boxShadow: 'var(--shadow-md)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px',
                fontSize: '0.75rem',
                zIndex: 100,
                maxWidth: '280px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                <span className="font-mono" style={{ color: '#D6A62C', fontWeight: 700 }}>
                  #{hoverPosition.node.shortIdx} {hoverPosition.node.id}
                </span>
                <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>
                  {hoverPosition.node.service || 'service'}
                </span>
              </div>
              {hoverPosition.node.evidence && (
                <div style={{ marginTop: '4px', color: 'var(--text-secondary)', fontSize: '0.7rem' }}>
                  {hoverPosition.node.evidence}
                </div>
              )}
            </div>
          )}

          {/* Zoom & Re-stabilize Controls */}
          <div
            style={{
              position: 'absolute',
              top: '12px',
              right: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              zIndex: 50,
            }}
          >
            <button
              onClick={handleZoomIn}
              title="Zoom In"
              style={{
                background: '#FAF8F0',
                border: '1px solid var(--border-subtle)',
                color: '#252525',
                width: '30px',
                height: '30px',
                borderRadius: 'var(--radius-full)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              onClick={handleZoomOut}
              title="Zoom Out"
              style={{
                background: '#FAF8F0',
                border: '1px solid var(--border-subtle)',
                color: '#252525',
                width: '30px',
                height: '30px',
                borderRadius: 'var(--radius-full)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <ZoomOut size={14} />
            </button>
            <button
              onClick={handleResetView}
              title="Reset View & Re-stabilize"
              style={{
                background: '#FAF8F0',
                border: '1px solid var(--border-subtle)',
                color: '#252525',
                width: '30px',
                height: '30px',
                borderRadius: 'var(--radius-full)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <RotateCcw size={13} />
            </button>
          </div>

          {/* Legend Overlay with Distinct Strong Edge Color */}
          <div
            style={{
              position: 'absolute',
              bottom: '12px',
              left: '12px',
              background: 'rgba(250, 248, 240, 0.95)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-full)',
              padding: '6px 14px',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: '12px',
              fontSize: '0.72rem',
              backdropFilter: 'blur(8px)',
              boxShadow: 'var(--shadow-md)',
              zIndex: 50,
            }}
          >
            {/* Distinct Strong Edge Color Legend Item */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '16px', height: '4px', background: STRONG_EDGE.stroke, borderRadius: 'var(--radius-full)' }} />
              <strong style={{ color: '#785A00' }}>Strong Edge</strong>
            </div>

            {/* Service Node Colors */}
            {Object.entries(SERVICE_COLORS).map(([key, item]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: item.fill }} />
                <span style={{ color: 'var(--text-secondary)' }}>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Node Inspector Side Panel */}
      <div
        className="glass-card"
        style={{
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          maxHeight: '620px',
          overflowY: 'auto',
          borderRadius: 'var(--radius-xl)',
        }}
      >
        {/* Panel Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)',
            paddingBottom: '10px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Info size={16} color={STRONG_EDGE.stroke} />
            <h4 style={{ fontSize: '0.88rem', fontWeight: 600 }}>Evidence Inspector</h4>
          </div>
          {selectedNode && (
            <span
              className="badge badge-amber font-mono"
              style={{
                fontSize: '0.7rem',
              }}
            >
              Node #{selectedNode.shortIdx}
            </span>
          )}
        </div>

        {/* Quick Node Search */}
        <div style={{ position: 'relative' }}>
          <Search
            size={13}
            color="var(--text-muted)"
            style={{ position: 'absolute', left: '12px', top: '10px' }}
          />
          <input
            type="text"
            placeholder="Search signals by ID or service..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 12px 7px 34px',
              fontSize: '0.75rem',
              background: '#FFFFFF',
              border: '1px solid rgba(61, 70, 84, 0.2)',
              borderRadius: 'var(--radius-full)',
              color: 'var(--text-primary)',
            }}
          />
        </div>

        {selectedNode ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Selected Node Details Card */}
            <div
              style={{
                padding: '14px',
                background: '#F2EFE5',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span className="font-mono" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#252525' }}>
                  #{selectedNode.shortIdx} {selectedNode.id}
                </span>
                <span className="badge badge-purple" style={{ fontSize: '0.68rem' }}>
                  {selectedNode.type || 'anomaly'}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '0.74rem', marginTop: '6px' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Service: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{selectedNode.service || 'N/A'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Component: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{selectedNode.component || 'N/A'}</strong>
                </div>
                {selectedNode.anomaly_score !== undefined && (
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Anomaly Score: </span>
                    <strong style={{ color: '#D6A62C' }}>{selectedNode.anomaly_score}</strong>
                  </div>
                )}
                {selectedNode.timestamp && (
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Time: </span>
                    <strong style={{ color: 'var(--text-secondary)' }}>
                      {formatIST(selectedNode.timestamp)}
                    </strong>
                  </div>
                )}
              </div>

              {selectedNode.evidence && (
                <div
                  style={{
                    marginTop: '10px',
                    padding: '8px 12px',
                    background: '#FAF8F0',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.72rem',
                    color: 'var(--text-primary)',
                    fontFamily: 'monospace',
                    wordBreak: 'break-word',
                  }}
                >
                  {selectedNode.evidence}
                </div>
              )}
            </div>

            {/* Connected Edges with Strong Color Badges */}
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '8px',
                }}
              >
                <span style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Connected Edges ({selectedNodeEdges.length})
                </span>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {viewMode === 'backbone' ? 'MST Backbone' : viewMode === 'top2' ? 'Top 2' : 'All Strong'}
                </span>
              </div>

              {selectedNodeEdges.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', padding: '12px 0', textAlign: 'center' }}>
                  No active strong edges connected to this node in current mode.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {selectedNodeEdges.map((edge, idx) => {
                    const targetNode = edge.targetNode;
                    return (
                      <div
                        key={idx}
                        onClick={() => setSelectedNodeId(edge.targetId)}
                        style={{
                          padding: '10px 12px',
                          background: '#F2EFE5',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-md)',
                          cursor: 'pointer',
                          transition: 'border-color 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#D6A62C')}
                        onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: '6px',
                          }}
                        >
                          <span
                            className="font-mono"
                            style={{
                              color: 'var(--text-primary)',
                              fontWeight: 600,
                              fontSize: '0.74rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <ChevronRight size={12} color="#D6A62C" />
                            #{targetNode?.shortIdx || '?'} {targetNode?.service || edge.targetId}
                          </span>
                          <span
                            className="badge badge-amber font-mono"
                            style={{
                              fontSize: '0.7rem',
                            }}
                          >
                            Weight: {edge.weight.toFixed(2)}
                          </span>
                        </div>

                        {/* Multi-Dimensional Correlation Scores */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(5, 1fr)',
                            gap: '4px',
                            fontSize: '0.64rem',
                            color: 'var(--text-secondary)',
                            background: '#FAF8F0',
                            padding: '5px 8px',
                            borderRadius: 'var(--radius-md)',
                            textAlign: 'center',
                          }}
                        >
                          <div><span style={{ color: '#807663' }}>Temporal:</span> <strong>{(edge.temporal ?? 0).toFixed(2)}</strong></div>
                          <div><span style={{ color: '#807663' }}>Service:</span> <strong>{(edge.service ?? 0).toFixed(2)}</strong></div>
                          <div><span style={{ color: '#807663' }}>Component:</span> <strong>{(edge.component ?? 0).toFixed(2)}</strong></div>
                          <div><span style={{ color: '#807663' }}>Topo:</span> <strong>{(edge.topology ?? 0).toFixed(2)}</strong></div>
                          <div><span style={{ color: '#807663' }}>Evidence:</span> <strong>{(edge.evidence_similarity ?? 0).toFixed(2)}</strong></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Quick Node List */}
            {filteredNodesList.length > 0 && (
              <div>
                <span style={{ fontSize: '0.74rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
                  All Nodes in Cluster ({filteredNodesList.length})
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', maxHeight: '120px', overflowY: 'auto' }}>
                  {filteredNodesList.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => setSelectedNodeId(n.id)}
                      style={{
                        padding: '4px 10px',
                        fontSize: '0.68rem',
                        fontFamily: 'monospace',
                        borderRadius: 'var(--radius-full)',
                        border: selectedNodeId === n.id ? '1px solid #D6A62C' : '1px solid var(--border-subtle)',
                        background: selectedNodeId === n.id ? 'rgba(214, 166, 44, 0.16)' : '#EAE6DB',
                        color: selectedNodeId === n.id ? '#785A00' : 'var(--text-secondary)',
                        cursor: 'pointer',
                        fontWeight: selectedNodeId === n.id ? 700 : 500,
                      }}
                    >
                      #{n.shortIdx} {n.shortId}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: '30px 0' }}>
            Click on any node in the graph or select from the list above to inspect its multi-dimensional correlation edge weights.
          </div>
        )}
      </div>
    </div>
  );
}
