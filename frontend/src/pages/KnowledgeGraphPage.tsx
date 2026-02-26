import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Search,
  Users,
  Building2,
  Mail,
  GitBranch,
  X,
  Loader2,
  AlertCircle,
  Filter,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Badge } from '../components/ui';
import { graphApi } from '../api/graph';
import { clsx } from 'clsx';

interface GraphNode {
  id: string;
  name: string;
  type: 'Prospect' | 'Company' | 'Sequence';
  val: number;
  color: string;
}

interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
}

const nodeColors: Record<string, string> = {
  Prospect: '#8B5CF6',
  Company: '#10B981',
  Sequence: '#F59E0B',
  Email: '#3B82F6',
};

export function KnowledgeGraphPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    Prospect: true,
    Company: true,
    Sequence: true,
  });

  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useQuery({
    queryKey: ['graph', 'stats'],
    queryFn: () => graphApi.getStats(),
    retry: 1,
  });

  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] }>({
    nodes: [],
    links: [],
  });

  const [isLoadingGraph, setIsLoadingGraph] = useState(false);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight - 60,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const loadGraphData = useCallback(async () => {
    setIsLoadingGraph(true);
    try {
      const nodes: GraphNode[] = [];
      const links: GraphEdge[] = [];

      if (filters.Prospect) {
        const prospectResults = await graphApi.search('', ['Prospect'], 50);
        prospectResults.results.forEach((r: any) => {
          const p = r.p?.properties || r;
          nodes.push({
            id: `prospect-${p.email}`,
            name: p.first_name && p.last_name ? `${p.first_name} ${p.last_name}` : p.email,
            type: 'Prospect',
            val: 5,
            color: nodeColors.Prospect,
          });
        });
      }

      if (filters.Company) {
        const companyResults = await graphApi.search('', ['Company'], 30);
        companyResults.results.forEach((r: any) => {
          const c = r.c?.properties || r;
          nodes.push({
            id: `company-${c.domain}`,
            name: c.name || c.domain,
            type: 'Company',
            val: 10,
            color: nodeColors.Company,
          });
          links.push({
            source: `company-${c.domain}`,
            target: `company-${c.domain}`,
          });
        });
      }

      if (filters.Sequence) {
        const sequenceResults = await graphApi.search('', ['Sequence'], 20);
        sequenceResults.results.forEach((r: any) => {
          const s = r.s?.properties || r;
          nodes.push({
            id: `sequence-${s.name}`,
            name: s.name,
            type: 'Sequence',
            val: 8,
            color: nodeColors.Sequence,
          });
        });
      }

      setGraphData({ nodes, links });
    } catch (err) {
      console.error('Failed to load graph data:', err);
    } finally {
      setIsLoadingGraph(false);
    }
  }, [filters]);

  useEffect(() => {
    loadGraphData();
  }, [loadGraphData]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadGraphData();
      return;
    }

    setIsLoadingGraph(true);
    try {
      const results = await graphApi.search(searchQuery, undefined, 30);
      const nodes: GraphNode[] = [];

      results.results.forEach((r: any) => {
        const type = r.type || 'Prospect';
        const props = r.p?.properties || r.c?.properties || r.s?.properties || r;

        nodes.push({
          id: `${type.toLowerCase()}-${props.email || props.domain || props.name}`,
          name: props.first_name && props.last_name
            ? `${props.first_name} ${props.last_name}`
            : props.email || props.name || props.domain,
          type: type as 'Prospect' | 'Company' | 'Sequence',
          val: 8,
          color: nodeColors[type] || '#6B7280',
        });
      });

      setGraphData({ nodes, links: [] });
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsLoadingGraph(false);
    }
  };

  const handleNodeClick = (node: any) => {
    const graphNode = node as GraphNode;
    setSelectedNode(graphNode);
  };

  const filteredNodes = graphData.nodes.filter((node) => filters[node.type]);

  const isDegraded = statsError || (stats && stats.prospect_count === 0 && stats.company_count === 0);

  return (
    <div className="h-full flex flex-col">
      <Header
        title="Knowledge Graph"
        subtitle="Visualize your prospect relationships"
      />

      <div className="flex-1 p-6 flex flex-col gap-4">
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search prospects, companies..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
            />
          </div>

          <Button
            variant="outline"
            onClick={() => setShowFilters(!showFilters)}
            className={clsx(showFilters && 'bg-brand-purple/10')}
          >
            <Filter className="h-4 w-4 mr-2" />
            Filters
          </Button>

          <Button variant="outline" onClick={loadGraphData} disabled={isLoadingGraph}>
            <Loader2 className={clsx('h-4 w-4 mr-2', isLoadingGraph && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {showFilters && (
          <Card className="py-3">
            <div className="flex items-center gap-6">
              <span className="text-sm font-medium text-slate-600">Show:</span>
              {Object.entries(filters).map(([type, enabled]) => (
                <label key={type} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => setFilters({ ...filters, [type]: e.target.checked })}
                    className="h-4 w-4 rounded border-slate-300 text-brand-purple"
                  />
                  <span className="text-sm text-slate-700">{type}s</span>
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: nodeColors[type] }}
                  />
                </label>
              ))}
            </div>
          </Card>
        )}

        <div className="grid grid-cols-4 gap-4">
          <Card className="py-3 px-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-100">
                <Users className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {statsLoading ? '-' : stats?.prospect_count || 0}
                </p>
                <p className="text-xs text-slate-500">Prospects</p>
              </div>
            </div>
          </Card>

          <Card className="py-3 px-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-100">
                <Building2 className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {statsLoading ? '-' : stats?.company_count || 0}
                </p>
                <p className="text-xs text-slate-500">Companies</p>
              </div>
            </div>
          </Card>

          <Card className="py-3 px-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-100">
                <GitBranch className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {statsLoading ? '-' : stats?.sequence_count || 0}
                </p>
                <p className="text-xs text-slate-500">Sequences</p>
              </div>
            </div>
          </Card>

          <Card className="py-3 px-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-100">
                <Mail className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {statsLoading ? '-' : stats?.email_count || 0}
                </p>
                <p className="text-xs text-slate-500">Emails</p>
              </div>
            </div>
          </Card>
        </div>

        {isDegraded && !statsLoading && (
          <Card className="py-8">
            <div className="text-center">
              <AlertCircle className="h-12 w-12 text-amber-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                FalkorDB Not Connected
              </h3>
              <p className="text-slate-500 max-w-md mx-auto">
                The knowledge graph is currently unavailable. Please ensure FalkorDB is
                provisioned and the environment variables are configured correctly.
              </p>
            </div>
          </Card>
        )}

        <div className="flex-1 flex gap-4 min-h-0">
          <Card className="flex-1 overflow-hidden">
            {!statsLoading && !isDegraded && (
              <div ref={containerRef} className="w-full h-full">
                {isLoadingGraph ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <Loader2 className="h-8 w-8 text-brand-purple animate-spin" />
                  </div>
                ) : (
                  <ForceGraph2D
                    ref={graphRef}
                    graphData={{ nodes: filteredNodes, links: [] }}
                    nodeLabel="name"
                    nodeColor={(node) => (node as GraphNode).color}
                    nodeVal="val"
                    linkColor={() => '#CBD5E1'}
                    backgroundColor="#F8FAFC"
                    width={dimensions.width}
                    height={dimensions.height}
                    onNodeClick={handleNodeClick}
                    nodeCanvasObject={(node, ctx, globalScale) => {
                      const graphNode = node as GraphNode;
                      const label = graphNode.name;
                      const fontSize = 12 / globalScale;
                      const nodeR = 5;

                      ctx.beginPath();
                      ctx.arc(node.x!, node.y!, nodeR, 0, 2 * Math.PI, false);
                      ctx.fillStyle = graphNode.color;
                      ctx.fill();

                      ctx.font = `${fontSize}px Sans-Serif`;
                      ctx.textAlign = 'center';
                      ctx.textBaseline = 'middle';
                      ctx.fillStyle = '#1E293B';
                      ctx.fillText(label, node.x!, node.y! + nodeR + fontSize);
                    }}
                  />
                )}
              </div>
            )}
          </Card>

          {selectedNode && (
            <Card className="w-80 flex-shrink-0">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Node Details</CardTitle>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedNode(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <div className="px-4 pb-4 space-y-3">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide">Name</p>
                  <p className="font-medium text-slate-900">{selectedNode.name}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide">Type</p>
                  <Badge
                    className={clsx(
                      'mt-1',
                      selectedNode.type === 'Prospect' && 'bg-purple-100 text-purple-700',
                      selectedNode.type === 'Company' && 'bg-green-100 text-green-700',
                      selectedNode.type === 'Sequence' && 'bg-amber-100 text-amber-700'
                    )}
                  >
                    {selectedNode.type}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide">ID</p>
                  <p className="text-sm text-slate-600 font-mono truncate">{selectedNode.id}</p>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default KnowledgeGraphPage;
