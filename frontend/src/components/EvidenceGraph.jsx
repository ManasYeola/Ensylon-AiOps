import React, { useEffect, useRef, useState } from 'react';
import { Network, Info, Sliders, Eye, RefreshCcw } from 'lucide-react';

export default function EvidenceGraph({ incident, graphData }) {
  const canvasRef = useRef(null);
  const [threshold, setThreshold] = useState(0.70);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);

  const nodesRef = useRef([]);
  const edgesRef = useRef([]);
  const animationFrameRef = useRef(null);

  // Parse nodes and edges from graphData
  useEffect(() => {
    if (!graphData || !graphData.nodes) return;

    const rawNodes = graphData.nodes_data || graphData.nodes.map((id) => ({ id }));
    const rawEdges = graphData.edges || [];

    // Initialize node positions in a circle layout with slight jitter
    const width = canvasRef.current ? canvasRef.current.clientWidth : 700;
    const height = canvasRef.current ? canvasRef.current.clientHeight : 450;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.35;

    const n = rawNodes.length;
    nodesRef.current = rawNodes.map((node, i) => {
      const angle = (i / n) * 2 * Math.PI;
      return {
        ...node,
        id: node.id,
        x: centerX + radius * Math.cos(angle) + (Math.random() - 0.5) * 20,
        y: centerY + radius * Math.sin(angle) + (Math.random() - 0.5) * 20,
        vx: 0,
        vy: 0,
        radius: 18,
      };
    });

    edgesRef.current = rawEdges;
    if (nodesRef.current.length > 0 && !selectedNode) {
      setSelectedNode(nodesRef.current[0]);
    }
  }, [graphData]);

  // Force simulation loop on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let isRunning = true;

    const render = () => {
      if (!isRunning) return;

      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const centerX = width / 2;
      const centerY = height / 2;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;

      // Simple force simulation
      // 1. Repulsion between nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 200) {
            const force = (200 - dist) / dist * 0.08;
            nodes[i].vx -= dx * force;
            nodes[i].vy -= dy * force;
            nodes[j].vx += dx * force;
            nodes[j].vy += dy * force;
          }
        }
      }

      // 2. Spring attraction along edges with weight >= threshold
      edges.forEach((edge) => {
        if (edge.weight < threshold) return;
        const source = nodes.find((n) => n.id === edge.source_signal);
        const target = nodes.find((n) => n.id === edge.target_signal);
        if (source && target) {
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const targetDist = 120 * (1 - edge.weight * 0.4);
          const force = (dist - targetDist) * 0.005 * edge.weight;
          source.vx += (dx / dist) * force;
          source.vy += (dy / dist) * force;
          target.vx -= (dx / dist) * force;
          target.vy -= (dy / dist) * force;
        }
      });

      // 3. Gravity towards center & friction damping
      nodes.forEach((node) => {
        node.vx += (centerX - node.x) * 0.005;
        node.vy += (centerY - node.y) * 0.005;
        node.vx *= 0.85;
        node.vy *= 0.85;
        node.x += node.vx;
        node.y += node.vy;

        // Bounding box padding
        node.x = Math.max(30, Math.min(width - 30, node.x));
        node.y = Math.max(30, Math.min(height - 30, node.y));
      });

      // Clear canvas
      ctx.clearRect(0, 0, width, height);

      // Draw background grid dots
      ctx.fillStyle = 'rgba(255, 255, 255, 0.03)';
      for (let x = 15; x < width; x += 30) {
        for (let y = 15; y < height; y += 30) {
          ctx.beginPath();
          ctx.arc(x, y, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Draw edges
      edges.forEach((edge) => {
        if (edge.weight < threshold) return;
        const source = nodes.find((n) => n.id === edge.source_signal);
        const target = nodes.find((n) => n.id === edge.target_signal);
        if (!source || !target) return;

        const isHighlighted =
          (selectedNode && (selectedNode.id === source.id || selectedNode.id === target.id)) ||
          (hoveredNode && (hoveredNode.id === source.id || hoveredNode.id === target.id));

        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);

        if (isHighlighted) {
          ctx.strokeStyle = '#06B6D4';
          ctx.lineWidth = 2.5;
          ctx.shadowColor = '#06B6D4';
          ctx.shadowBlur = 8;
        } else if (edge.weight >= 0.70) {
          ctx.strokeStyle = `rgba(6, 182, 212, ${Math.min(0.8, edge.weight)})`;
          ctx.lineWidth = 1.5;
          ctx.shadowBlur = 0;
        } else {
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
          ctx.lineWidth = 1;
          ctx.shadowBlur = 0;
        }
        ctx.stroke();
        ctx.shadowBlur = 0;
      });

      // Draw nodes
      nodes.forEach((node) => {
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hoveredNode?.id === node.id;

        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);

        // Fill based on service or role
        if (node.service?.includes('payment')) {
          ctx.fillStyle = isSelected ? '#06B6D4' : '#0E7490';
        } else if (node.service?.includes('order')) {
          ctx.fillStyle = isSelected ? '#8B5CF6' : '#6D28D9';
        } else {
          ctx.fillStyle = isSelected ? '#3B82F6' : '#1D4ED8';
        }

        ctx.fill();

        // Node stroke / glow
        ctx.strokeStyle = isSelected ? '#FFFFFF' : isHovered ? '#06B6D4' : 'rgba(255, 255, 255, 0.25)';
        ctx.lineWidth = isSelected ? 3 : 1.5;
        if (isSelected || isHovered) {
          ctx.shadowColor = '#06B6D4';
          ctx.shadowBlur = 12;
        }
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Label
        ctx.fillStyle = '#FFFFFF';
        ctx.font = '600 11px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(node.id, node.x, node.y);
      });

      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      isRunning = false;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [threshold, selectedNode, hoveredNode]);

  // Handle canvas clicks & mouse movement
  const handleCanvasClick = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const clicked = nodesRef.current.find((node) => {
      const dx = node.x - x;
      const dy = node.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= node.radius + 4;
    });

    if (clicked) {
      setSelectedNode(clicked);
    }
  };

  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const hovered = nodesRef.current.find((node) => {
      const dx = node.x - x;
      const dy = node.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= node.radius + 4;
    });

    setHoveredNode(hovered || null);
    canvas.style.cursor = hovered ? 'pointer' : 'default';
  };

  // Connected edges for the selected node
  const connectedEdges = selectedNode
    ? (edgesRef.current || []).filter(
        (e) =>
          (e.source_signal === selectedNode.id || e.target_signal === selectedNode.id) &&
          e.weight >= threshold
      )
    : [];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
      {/* Canvas viewport */}
      <div className="glass-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column' }}>
        {/* Controls header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '12px',
          paddingBottom: '12px',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Network size={18} color="var(--cyan)" />
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600 }}>
              Evidence Graph ({nodesRef.current.length} Nodes, {edgesRef.current.filter(e => e.weight >= threshold).length} Active Edges)
            </h4>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Threshold Slider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem' }}>
              <Sliders size={14} color="var(--text-secondary)" />
              <span style={{ color: 'var(--text-secondary)' }}>Strong Edge Filter:</span>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                style={{ width: '90px', accentColor: 'var(--cyan)' }}
              />
              <span className="font-mono badge badge-cyan" style={{ fontSize: '0.7rem' }}>
                &ge; {threshold.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Canvas */}
        <div style={{ flex: 1, minHeight: '420px', position: 'relative' }}>
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            onMouseMove={handleMouseMove}
            style={{ width: '100%', height: '100%', display: 'block', borderRadius: 'var(--radius-md)' }}
          />

          {/* Legend overlay */}
          <div style={{
            position: 'absolute',
            bottom: '12px',
            left: '12px',
            background: 'rgba(10, 16, 28, 0.85)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            fontSize: '0.72rem',
            backdropFilter: 'blur(8px)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#06B6D4' }} />
              <span>Payment API</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#8B5CF6' }} />
              <span>Order Worker</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{ width: '14px', height: '2px', background: '#06B6D4' }} />
              <span>Strong Edge (&ge; 0.70)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Node Inspector Side Panel */}
      <div className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
          <Info size={16} color="var(--cyan)" />
          <h4 style={{ fontSize: '0.9rem', fontWeight: 600 }}>Node & Edge Inspector</h4>
        </div>

        {selectedNode ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.8rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span className="font-mono" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--cyan)' }}>
                  {selectedNode.id}
                </span>
                <span className="badge badge-purple">{selectedNode.type || 'anomaly'}</span>
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Service: <strong style={{ color: 'var(--text-primary)' }}>{selectedNode.service || 'N/A'}</strong> / {selectedNode.component || 'N/A'}
              </div>
              {selectedNode.message && (
                <div style={{
                  marginTop: '8px',
                  padding: '8px 10px',
                  background: 'var(--bg-card)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.75rem',
                  fontStyle: 'italic',
                  color: 'var(--text-secondary)',
                }}>
                  &ldquo;{selectedNode.message}&rdquo;
                </div>
              )}
            </div>

            {/* Dimensional Edges */}
            <div>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                Connected Edges ({connectedEdges.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto' }}>
                {connectedEdges.map((edge, idx) => {
                  const otherNodeId = edge.source_signal === selectedNode.id ? edge.target_signal : edge.source_signal;
                  return (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span className="font-mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                          &harr; {otherNodeId}
                        </span>
                        <span className="badge badge-cyan font-mono" style={{ fontSize: '0.7rem' }}>
                          Weight: {edge.weight?.toFixed(2)}
                        </span>
                      </div>
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: '4px',
                        fontSize: '0.68rem',
                        color: 'var(--text-muted)',
                      }}>
                        <span>Temp: {edge.temporal?.toFixed(2)}</span>
                        <span>Svc: {edge.service?.toFixed(2)}</span>
                        <span>Topo: {edge.topology?.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: '20px 0' }}>
            Click on any node in the graph to inspect its multi-dimensional correlation edge weights.
          </div>
        )}
      </div>
    </div>
  );
}
