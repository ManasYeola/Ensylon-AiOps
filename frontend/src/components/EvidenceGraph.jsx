import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  Network,
  Info,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  Eye,
  ChevronRight,
  Sparkles,
} from 'lucide-react';

// Service color scheme for distinct visual clustering
const SERVICE_COLORS = {
  payment: { fill: '#06B6D4', stroke: '#22D3EE', label: 'Payment API' },
  order: { fill: '#A855F7', stroke: '#C084FC', label: 'Order Worker' },
  docforge: { fill: '#10B981', stroke: '#34D399', label: 'DocForge' },
  rulesforge: { fill: '#F59E0B', stroke: '#FBBF24', label: 'RulesForge' },
  agency: { fill: '#F43F5E', stroke: '#FB7185', label: 'Agency Gateway' },
  default: { fill: '#3B82F6', stroke: '#60A5FA', label: 'Core Service' },
};

// Distinct color for Strong Edges (Electric Lime / Chartreuse - completely distinct from Cyan, Purple, Green, Amber, Rose, Blue)
const STRONG_EDGE = {
  stroke: '#A3E635',
  highlight: '#BEF264',
  glow: 'rgba(163, 230, 53, 0.45)',
  badgeBg: '#0F172A',
  label: 'Strong Correlation Edge',
};

function getServiceColor(serviceName = '') {
  const s = String(serviceName).toLowerCase();
  if (s.includes('payment')) return SERVICE_COLORS.payment;
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

    // Subtle background grid
    const worldLeft = -transform.x / transform.k - 200;
    const worldTop = -transform.y / transform.k - 200;
    const worldRight = (width - transform.x) / transform.k + 200;
    const worldBottom = (height - transform.y) / transform.k + 200;

    ctx.fillStyle = 'rgba(255, 255, 255, 0.03)';
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

    // 1. Draw Edges using DISTINCT Strong Edge Color (Neon Lime #A3E635)
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
        // Glowing Neon Lime for active / focused edge
        ctx.strokeStyle = STRONG_EDGE.highlight;
        ctx.lineWidth = 2.8;
        ctx.shadowColor = STRONG_EDGE.glow;
        ctx.shadowBlur = 10;
      } else if (selectedNodeId || hoveredNodeId) {
        // Dimmed edges when focusing on a specific node
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.lineWidth = 1;
        ctx.shadowBlur = 0;
      } else {
        // Crisp Strong Edge in distinctive Neon Lime color
        ctx.strokeStyle = STRONG_EDGE.stroke;
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

        ctx.fillStyle = isHighlighted ? STRONG_EDGE.stroke : STRONG_EDGE.badgeBg;
        ctx.strokeStyle = isHighlighted ? '#FFFFFF' : STRONG_EDGE.stroke;
        ctx.lineWidth = 1.2;

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH, 4);
        } else {
          ctx.rect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isHighlighted ? '#0F172A' : STRONG_EDGE.highlight;
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
      ctx.fillStyle = isSelected ? '#FFFFFF' : isHovered ? color.stroke : color.fill;
      ctx.fill();

      // Stroke & Glow
      ctx.strokeStyle = isSelected ? STRONG_EDGE.highlight : isHovered ? '#FFFFFF' : color.stroke;
      ctx.lineWidth = isSelected ? 3.5 : isHovered ? 2.5 : 1.5;
      if (isSelected || isHovered) {
        ctx.shadowColor = STRONG_EDGE.glow;
        ctx.shadowBlur = 12;
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Clean Number Inside Circle
      ctx.fillStyle = isSelected ? '#0F172A' : '#FFFFFF';
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

        ctx.fillStyle = 'rgba(15, 23, 42, 0.94)';
        ctx.strokeStyle = isSelected ? STRONG_EDGE.stroke : 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(node.x - lw / 2, ly - lh / 2, lw, lh, 4);
        } else {
          ctx.rect(node.x - lw / 2, ly - lh / 2, lw, lh);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? STRONG_EDGE.highlight : '#F8FAFC';
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
      <div className="glass-card" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <Network size={36} color="var(--cyan)" style={{ margin: '0 auto 16px', display: 'block', opacity: 0.8 }} />
        <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>Loading Evidence Graph...</h4>
        <p style={{ fontSize: '0.82rem', marginTop: '6px' }}>Fetching correlated signal nodes and dimensional edges</p>
      </div>
    );
  }

  if (!graphData.nodes || graphData.nodes.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <Network size={36} color="var(--text-muted)" style={{ margin: '0 auto 16px', display: 'block' }} />
        <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>No Signal Nodes in Cluster</h4>
        <p style={{ fontSize: '0.82rem', marginTop: '6px' }}>This incident does not contain active anomalous signal nodes.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '16px' }}>
      {/* Canvas Viewport */}
      <div className="glass-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column' }}>
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
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Evidence Graph
            </h4>
            <span className="badge badge-cyan font-mono" style={{ fontSize: '0.72rem' }}>
              {rawNodes.length} Nodes
            </span>
            <span
              className="badge font-mono"
              style={{
                fontSize: '0.72rem',
                background: 'rgba(163, 230, 53, 0.15)',
                border: '1px solid #A3E635',
                color: '#A3E635',
              }}
            >
              {activeEdges.length} Strong Edges
            </span>
          </div>

          {/* View Mode & Weight Label Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {/* View Mode Selector */}
            <div
              style={{
                display: 'flex',
                background: 'rgba(15, 23, 42, 0.8)',
                padding: '2px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <button
                onClick={() => setViewMode('backbone')}
                title="Maximum Spanning Tree: clean correlation backbone with zero hairball cycles"
                style={{
                  padding: '4px 9px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-xs)',
                  cursor: 'pointer',
                  background: viewMode === 'backbone' ? STRONG_EDGE.stroke : 'transparent',
                  color: viewMode === 'backbone' ? '#0F172A' : 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <Sparkles size={12} />
                Clean Backbone
              </button>
              <button
                onClick={() => setViewMode('top2')}
                title="Top 2 strongest connections per node"
                style={{
                  padding: '4px 9px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-xs)',
                  cursor: 'pointer',
                  background: viewMode === 'top2' ? STRONG_EDGE.stroke : 'transparent',
                  color: viewMode === 'top2' ? '#0F172A' : 'var(--text-secondary)',
                }}
              >
                Top-2
              </button>
              <button
                onClick={() => setViewMode('all')}
                title="Show all strong correlation edges"
                style={{
                  padding: '4px 9px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-xs)',
                  cursor: 'pointer',
                  background: viewMode === 'all' ? STRONG_EDGE.stroke : 'transparent',
                  color: viewMode === 'all' ? '#0F172A' : 'var(--text-secondary)',
                }}
              >
                All Strong
              </button>
            </div>

            {/* Weight Labels Mode Toggle */}
            <button
              onClick={() => setWeightMode((prev) => (prev === 'focus' ? 'all' : 'focus'))}
              title="Toggle whether edge weight badges appear on hover/selection or across all edges"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 8px',
                fontSize: '0.72rem',
                fontWeight: 500,
                background: weightMode === 'all' ? 'rgba(163, 230, 53, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                border: weightMode === 'all' ? `1px solid ${STRONG_EDGE.stroke}` : '1px solid var(--border-subtle)',
                color: weightMode === 'all' ? STRONG_EDGE.stroke : 'var(--text-secondary)',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
              }}
            >
              <Eye size={12} />
              <span>{weightMode === 'focus' ? 'Weights: Focus' : 'Weights: All'}</span>
            </button>
          </div>
        </div>

        {/* Stable Static Canvas Viewport */}
        <div style={{ flex: 1, minHeight: '440px', position: 'relative', overflow: 'hidden' }}>
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
              borderRadius: 'var(--radius-md)',
              background: '#0B1120',
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
                background: 'rgba(15, 23, 42, 0.95)',
                border: `1px solid ${STRONG_EDGE.stroke}`,
                boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 12px',
                fontSize: '0.75rem',
                zIndex: 100,
                maxWidth: '280px',
                backdropFilter: 'blur(8px)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                <span className="font-mono" style={{ color: STRONG_EDGE.stroke, fontWeight: 700 }}>
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
                background: 'rgba(15, 23, 42, 0.85)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-xs)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              onClick={handleZoomOut}
              title="Zoom Out"
              style={{
                background: 'rgba(15, 23, 42, 0.85)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-xs)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <ZoomOut size={14} />
            </button>
            <button
              onClick={handleResetView}
              title="Reset View & Re-stabilize"
              style={{
                background: 'rgba(15, 23, 42, 0.85)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-xs)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
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
              background: 'rgba(10, 16, 28, 0.90)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 12px',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: '12px',
              fontSize: '0.72rem',
              backdropFilter: 'blur(8px)',
              zIndex: 50,
            }}
          >
            {/* Distinct Strong Edge Color Legend Item */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '16px', height: '3px', background: STRONG_EDGE.stroke, borderRadius: '2px' }} />
              <strong style={{ color: STRONG_EDGE.stroke }}>Strong Edge</strong>
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
              className="badge font-mono"
              style={{
                fontSize: '0.7rem',
                background: 'rgba(163, 230, 53, 0.15)',
                border: '1px solid #A3E635',
                color: '#A3E635',
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
            style={{ position: 'absolute', left: '10px', top: '9px' }}
          />
          <input
            type="text"
            placeholder="Search signals by ID or service..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '6px 10px 6px 30px',
              fontSize: '0.75rem',
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
            }}
          />
        </div>

        {selectedNode ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Selected Node Details Card */}
            <div
              style={{
                padding: '12px',
                background: 'rgba(15, 23, 42, 0.7)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span className="font-mono" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#FFFFFF' }}>
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
                    <strong style={{ color: STRONG_EDGE.stroke }}>{selectedNode.anomaly_score}</strong>
                  </div>
                )}
                {selectedNode.timestamp && (
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Time: </span>
                    <strong style={{ color: 'var(--text-secondary)' }}>
                      {new Date(selectedNode.timestamp).toLocaleTimeString()}
                    </strong>
                  </div>
                )}
              </div>

              {selectedNode.evidence && (
                <div
                  style={{
                    marginTop: '10px',
                    padding: '8px 10px',
                    background: 'rgba(0, 0, 0, 0.3)',
                    borderRadius: 'var(--radius-xs)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.72rem',
                    color: 'var(--text-secondary)',
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
                          padding: '10px',
                          background: 'rgba(15, 23, 42, 0.6)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          cursor: 'pointer',
                          transition: 'border-color 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.borderColor = STRONG_EDGE.stroke)}
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
                            <ChevronRight size={12} color={STRONG_EDGE.stroke} />
                            #{targetNode?.shortIdx || '?'} {targetNode?.service || edge.targetId}
                          </span>
                          <span
                            className="badge font-mono"
                            style={{
                              fontSize: '0.7rem',
                              background: 'rgba(163, 230, 53, 0.15)',
                              border: `1px solid ${STRONG_EDGE.stroke}`,
                              color: STRONG_EDGE.stroke,
                            }}
                          >
                            Weight: {edge.weight.toFixed(2)}
                          </span>
                        </div>

                        {/* Multi-Dimensional Correlation Scores */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(4, 1fr)',
                            gap: '4px',
                            fontSize: '0.65rem',
                            color: 'var(--text-muted)',
                            background: 'rgba(0,0,0,0.2)',
                            padding: '4px 6px',
                            borderRadius: 'var(--radius-xs)',
                          }}
                        >
                          <span>Temporal: {(edge.temporal ?? 0).toFixed(2)}</span>
                          <span>Service: {(edge.service ?? 0).toFixed(2)}</span>
                          <span>Topo: {(edge.topology ?? 0).toFixed(2)}</span>
                          <span>Evidence: {(edge.evidence_similarity ?? 0).toFixed(2)}</span>
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
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxHeight: '120px', overflowY: 'auto' }}>
                  {filteredNodesList.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => setSelectedNodeId(n.id)}
                      style={{
                        padding: '3px 7px',
                        fontSize: '0.68rem',
                        fontFamily: 'monospace',
                        borderRadius: 'var(--radius-xs)',
                        border: selectedNodeId === n.id ? `1px solid ${STRONG_EDGE.stroke}` : '1px solid var(--border-subtle)',
                        background: selectedNodeId === n.id ? 'rgba(163, 230, 53, 0.2)' : 'rgba(15, 23, 42, 0.5)',
                        color: selectedNodeId === n.id ? STRONG_EDGE.stroke : 'var(--text-secondary)',
                        cursor: 'pointer',
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
