import React, { useMemo } from 'react';

interface GraphNode {
  id: string;
  x: number;
  y: number;
}

interface GraphEdge {
  from: string;
  to: string;
  verified: boolean;
}

interface GraphVisualizationProps {
  nodes: string[];
  edges: Array<{
    from: string;
    to: string;
    verified: boolean;
  }>;
  excludedNodes?: string[];
  width?: number;
  height?: number;
}

export function GraphVisualization({
  nodes,
  edges,
  excludedNodes = [],
  width = 600,
  height = 400,
}: GraphVisualizationProps) {
  // Calculate node positions in a circle layout
  const nodePositions = useMemo(() => {
    const positions: Map<string, GraphNode> = new Map();
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 60;

    nodes.forEach((nodeId, index) => {
      const angle = (2 * Math.PI * index) / nodes.length - Math.PI / 2;
      positions.set(nodeId, {
        id: nodeId,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      });
    });

    return positions;
  }, [nodes, width, height]);

  // Create unique edges (avoid duplicates for bidirectional edges)
  const uniqueEdges = useMemo(() => {
    const seen = new Set<string>();
    const result: GraphEdge[] = [];

    edges.forEach((edge) => {
      const key = [edge.from, edge.to].sort().join('-');
      if (!seen.has(key)) {
        seen.add(key);
        result.push(edge);
      }
    });

    return result;
  }, [edges]);

  const shortenId = (id: string) => {
    if (id.length <= 8) return id;
    return `${id.substring(0, 4)}...${id.substring(id.length - 4)}`;
  };

  return (
    <div className="border rounded-lg bg-white p-4">
      <svg width={width} height={height} className="mx-auto">
        {/* Draw edges */}
        {uniqueEdges.map((edge, index) => {
          const from = nodePositions.get(edge.from);
          const to = nodePositions.get(edge.to);
          if (!from || !to) return null;

          return (
            <line
              key={`edge-${index}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={edge.verified ? '#22c55e' : '#ef4444'}
              strokeWidth={2}
              opacity={0.6}
            />
          );
        })}

        {/* Draw nodes */}
        {nodes.map((nodeId) => {
          const pos = nodePositions.get(nodeId);
          if (!pos) return null;

          const isExcluded = excludedNodes.includes(nodeId);

          return (
            <g key={nodeId}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={20}
                fill={isExcluded ? '#fecaca' : '#dbeafe'}
                stroke={isExcluded ? '#ef4444' : '#3b82f6'}
                strokeWidth={2}
              />
              <text
                x={pos.x}
                y={pos.y + 35}
                textAnchor="middle"
                fontSize={10}
                fill="#374151"
              >
                {shortenId(nodeId)}
              </text>
              {isExcluded && (
                <text
                  x={pos.x}
                  y={pos.y + 5}
                  textAnchor="middle"
                  fontSize={14}
                  fill="#ef4444"
                >
                  ✗
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex justify-center gap-6 mt-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-blue-100 border-2 border-blue-500"></div>
          <span>Valid Node</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-red-100 border-2 border-red-500"></div>
          <span>Excluded Node</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-8 h-0.5 bg-green-500"></div>
          <span>Verified Edge</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-8 h-0.5 bg-red-500"></div>
          <span>Failed Edge</span>
        </div>
      </div>
    </div>
  );
}
