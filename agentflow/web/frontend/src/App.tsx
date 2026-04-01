import { useEffect, useState, useCallback } from 'react';
import type { Run, Health } from './api';
import { fetchRuns, fetchRun, cancelRun, rerunRun, fetchHealth } from './api';
import { Sidebar } from './Sidebar';
import { GraphView } from './GraphView';
import { Billboard } from './Billboard';
import { NodeDetail } from './NodeDetail';
import { RefreshCw, Cpu, Database, Activity, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isBillboardOpen, setIsBillboardOpen] = useState(false);

  const refreshRuns = useCallback(async () => {
     setLoading(true);
     try {
       const [data, healthData] = await Promise.all([fetchRuns(), fetchHealth()]);
       setRuns(data.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()));
       setHealth(healthData);
       if (data.length > 0 && !activeRunId) {
         setActiveRunId(data[0].id);
       }
     } catch (err) {
       console.error("Failed to fetch data:", err);
     } finally {
       setLoading(false);
     }
  }, [activeRunId]);

  const loadRun = useCallback(async (id: string) => {
     try {
       const run = await fetchRun(id);
       setActiveRun(run);
       if (!selectedNodeId && run.pipeline?.nodes?.length) {
         setSelectedNodeId(run.pipeline.nodes[0].id);
       }
     } catch (err) {
       console.error("Failed to load run details:", err);
     }
  }, [selectedNodeId]);

  const handleCancel = async () => {
    if (!activeRunId) return;
    try {
      await cancelRun(activeRunId);
      refreshRuns();
    } catch (err) {
      console.error("Cancel failed:", err);
    }
  };

  const handleRerun = async () => {
    if (!activeRunId) return;
    try {
      const newRun = await rerunRun(activeRunId);
      setActiveRunId(newRun.id);
      refreshRuns();
    } catch (err) {
      console.error("Rerun failed:", err);
    }
  };

  useEffect(() => {
    refreshRuns(); // Initial fetch
    
    // Poll for both runs and health to keep the UI in sync
    const metricsTimer = setInterval(async () => {
       try {
         const [data, healthData] = await Promise.all([fetchRuns(), fetchHealth()]);
         setRuns(data.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()));
         setHealth(healthData);
       } catch (e) {
         console.error("Polling error:", e);
       }
    }, 5000);
    
    return () => clearInterval(metricsTimer);
  }, [refreshRuns]);

  useEffect(() => {
    if (activeRunId) {
      loadRun(activeRunId);
      const timer = setInterval(() => loadRun(activeRunId), 3000);
      return () => clearInterval(timer);
    }
  }, [activeRunId, loadRun]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-900 overflow-hidden font-sans antialiased text-slate-800">
      {/* Top Header */}
      <header className="h-14 bg-slate-900 border-b border-slate-700 flex items-center px-6 shrink-0 justify-between shadow-2xl z-50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Cpu className="text-white w-5 h-5" />
          </div>
          <h1 className="text-white font-black tracking-tight text-xl italic uppercase">
            AgentFlow <span className="text-slate-500 font-normal ml-2 not-italic normal-case text-xs tracking-widest opacity-60">v0.1.0</span>
          </h1>
        </div>
        
        <div className="flex items-center gap-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
           <div className="flex items-center gap-2.5 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700/50">
             <Database className="w-3.5 h-3.5 text-blue-400" />
             TOTAL: {health?.runs.total || 0}
           </div>
           <div className="flex items-center gap-2.5 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700/50">
             <Clock className="w-3.5 h-3.5 text-amber-400" />
             QUEUED: {health?.runs.queued || 0}
           </div>
           <div className="flex items-center gap-2.5 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700/50">
             <Activity className={`w-3.5 h-3.5 text-emerald-400 ${(health?.runs.running || 0) > 0 ? 'animate-pulse' : ''}`} />
             RUNNING: {health?.runs.running || 0}
           </div>

           <div className="h-6 w-px bg-slate-700/50" />

           <div className="flex gap-2">
             <button 
               onClick={handleRerun} 
               disabled={!activeRunId}
               className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-30 text-white rounded-lg text-[10px] font-black transition-all border border-blue-400/20 shadow-lg shadow-blue-900/20 active:scale-95"
             >
               RERUN
             </button>
             <button 
               onClick={handleCancel} 
               disabled={!activeRunId || !['running', 'queued', 'pending', 'retrying'].includes(activeRun?.status || '')}
               className="px-4 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-20 text-white rounded-lg text-[10px] font-black transition-all border border-red-500/20 shadow-lg shadow-red-900/20 active:scale-95"
             >
               STOP
             </button>
           </div>

           <button onClick={refreshRuns} disabled={loading} className="p-2 hover:bg-slate-800 rounded-full transition-colors group">
             <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : 'text-slate-400 group-hover:text-white'}`} />
           </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex flex-1 overflow-hidden bg-white relative">
        <Sidebar 
           runs={runs} 
           activeRunId={activeRunId} 
           onSelectRun={(id) => { setActiveRunId(id); setSelectedNodeId(null); }} 
           onRefresh={refreshRuns} 
        />
        <div className="flex-1 flex flex-col min-w-0 border-x border-slate-200">
          <GraphView 
            run={activeRun} 
            onSelectNode={setSelectedNodeId} 
          />
        </div>

        {/* Persistent Billboard Toggle Handle (Visible when closed) */}
        {!isBillboardOpen && (
          <button 
             onClick={() => setIsBillboardOpen(true)}
             className="absolute right-0 top-1/2 -translate-y-1/2 w-8 h-40 bg-blue-600 hover:bg-blue-500 border border-blue-400 border-r-0 rounded-l-2xl flex flex-col items-center justify-center gap-4 transition-all z-[60] shadow-[0_0_20px_rgba(37,99,235,0.3)] group hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] active:scale-95 animate-in slide-in-from-right-2"
          >
             <ChevronLeft size={16} className="text-white group-hover:scale-110 transition-transform" />
             <span className="[writing-mode:vertical-lr] text-[10px] font-black tracking-[0.3em] uppercase text-white drop-shadow-sm">Billboard</span>
          </button>
        )}

        {/* Collapsible Billboard Drawer */}
        <div className={`flex shrink-0 transition-all duration-300 ease-in-out relative ${isBillboardOpen ? 'w-96 border-l border-slate-200 shadow-2xl' : 'w-0 overflow-hidden'}`}>
           {isBillboardOpen && (
             <button 
               onClick={() => setIsBillboardOpen(false)}
               title="Close Sidebar"
               className="absolute -left-4 top-1/2 -translate-y-1/2 w-4 h-14 bg-white border border-slate-200 shadow-lg rounded-l-xl flex items-center justify-center hover:bg-slate-50 transition-all z-[60] group cursor-pointer active:scale-95"
             >
               <ChevronRight size={14} className="text-slate-400" />
             </button>
           )}
           <div className="w-96 h-full flex flex-col bg-white">
             <Billboard runId={activeRunId} />
           </div>
        </div>

        <NodeDetail 
           runId={activeRunId}
           nodeId={selectedNodeId} 
           nodeState={activeRun?.nodes?.[selectedNodeId || ''] || null} 
           agentKind={activeRun?.pipeline?.nodes?.find(n => n.id === selectedNodeId)?.agent || activeRun?.pipeline?.nodes?.find(n => n.id === selectedNodeId)?.kind}
        />
      </main>
    </div>
  );
}

export default App;
