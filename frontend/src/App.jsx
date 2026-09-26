import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  ShieldAlert,
  Network,
  FileCheck,
  Layers,
  Sparkles,
} from 'lucide-react';
import Header from './components/Header';
import StatsBar from './components/StatsBar';
import Dashboard from './components/Dashboard';
import IncidentDetails from './components/IncidentDetails';
import EvidenceGraph from './components/EvidenceGraph';
import TicketReview from './components/TicketReview';
import { api } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // dashboard, details, graph, review
  const [health, setHealth] = useState(null);
  const [signals, setSignals] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [jiraTickets, setJiraTickets] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [graphData, setGraphData] = useState(null);

  const [isRunningDemo, setIsRunningDemo] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // Show a temporary toast message
  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  // Fetch all initial data
  const loadData = async () => {
    try {
      const [h, sList, incList, jList] = await Promise.allSettled([
        api.getHealth(),
        api.getSignals(),
        api.getIncidents(),
        api.getJiraTickets(),
      ]);

      if (h.status === 'fulfilled' && h.value) {
        setHealth(h.value);
        if (sList.status === 'fulfilled') {
          setSignals(sList.value || []);
        } else {
          setSignals([]);
        }
        if (jList.status === 'fulfilled') {
          setJiraTickets(jList.value || []);
        } else {
          setJiraTickets([]);
        }

        if (incList.status === 'fulfilled') {
          const loadedIncidents = incList.value || [];
          setIncidents(loadedIncidents);

          // Keep or select first incident
          if (loadedIncidents.length > 0) {
            setSelectedIncident((prev) => {
              if (prev) {
                const matched = loadedIncidents.find((i) => i.id === prev.id);
                if (
                  matched &&
                  matched.id === prev.id &&
                  matched.signal_ids?.length === prev.signal_ids?.length &&
                  matched.severity === prev.severity
                ) {
                  return prev;
                }
                return matched || loadedIncidents[0];
              }
              return loadedIncidents[0];
            });
          } else {
            setSelectedIncident(null);
          }
        } else {
          setIncidents([]);
          setSelectedIncident(null);
        }
      } else {
        // Backend is offline / closed
        setHealth(null);
        setSignals([]);
        setIncidents([]);
        setSelectedIncident(null);
        setJiraTickets([]);
        setGraphData(null);
      }
    } catch (err) {
      console.error('Failed to load data:', err);
      setHealth(null);
      setSignals([]);
      setIncidents([]);
      setSelectedIncident(null);
      setJiraTickets([]);
      setGraphData(null);
    }
  };

  useEffect(() => {
    loadData();
    // Poll health periodically every 3s
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  // Fetch graph data whenever selected incident changes
  useEffect(() => {
    if (!selectedIncident) {
      setGraphData(null);
      return;
    }

    const loadGraph = async () => {
      try {
        const g = await api.getEvidenceGraph(selectedIncident.id);
        setGraphData(g);
      } catch (err) {
        console.error('Failed to load graph data:', err);
        setGraphData(null);
      }
    };

    loadGraph();
  }, [selectedIncident]);

  // Check live stream status instead of running manual demo
  const handleRunDemo = async () => {
    setIsRunningDemo(true);
    try {
      const res = await api.getStreamsStatus();
      const streams = res.streams || {};
      const connectedCount = Object.values(streams).filter(s => s.connected).length;
      showToast(
        `Live Streams: ${connectedCount} connected. Listening for anomalous signals...`
      );
    } catch (err) {
      console.error('Stream status error:', err);
      showToast(`Error checking streams: ${err.message}`);
    } finally {
      setIsRunningDemo(false);
    }
  };

  // Handle selecting an incident
  const handleSelectIncident = (inc) => {
    setSelectedIncident(inc);
  };

  // Handle Jira ticket published
  const handleTicketPublished = (ticket) => {
    setJiraTickets((prev) => [ticket, ...prev.filter((t) => t.id !== ticket.id)]);
    showToast(`Published to Jira: ${ticket.id} (${ticket.title})`);
  };

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'details', label: 'Incident & Gates', icon: ShieldAlert, count: incidents.length },
    { id: 'graph', label: 'Evidence Graph', icon: Network },
    { id: 'review', label: 'Ticket Review & Jira', icon: FileCheck, count: jiraTickets.length },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          background: 'rgba(15, 23, 42, 0.92)',
          backdropFilter: 'blur(12px)',
          border: '1px solid var(--border-highlight)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 20px',
          boxShadow: 'var(--shadow-lg)',
          color: 'var(--text-primary)',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          zIndex: 2000,
        }}>
          <Sparkles size={16} color="var(--cyan)" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Header */}
      <Header
        health={health}
        isRunningDemo={isRunningDemo}
        onRunDemo={handleRunDemo}
        onRefresh={loadData}
      />

      {/* Main Content Area */}
      <main style={{ padding: '0 28px 40px 28px', flex: 1 }}>
        {/* Navigation Tabs Bar */}
        <nav className="modern-navbar" aria-label="Main Navigation">
          <div className="modern-tabs-track">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`modern-tab-btn ${isActive ? 'active' : ''}`}
                >
                  <Icon size={16} color={isActive ? '#D6A62C' : '#807663'} />
                  <span>{tab.label}</span>
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className="modern-tab-badge">{tab.count}</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Active Incident Indicator Chip */}
          {selectedIncident ? (
            <div
              className="modern-nav-incident-chip"
              onClick={() => setActiveTab('details')}
              style={{ cursor: 'pointer' }}
              title="Click to view Incident & Validation Gates"
            >
              <div className="live-pulse" />
              <span style={{
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: '#807663',
              }}>
                Active Incident
              </span>
              <span className="font-mono badge badge-amber">
                {selectedIncident.id}
              </span>
              <span className="badge badge-purple">
                {(selectedIncident.services || []).join(', ')}
              </span>
            </div>
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '6px 14px',
                background: 'rgba(234, 230, 219, 0.5)',
                borderRadius: '10px',
                fontSize: '0.78rem',
                color: '#807663',
              }}
            >
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: '#10B981',
                  boxShadow: '0 0 6px rgba(16, 185, 129, 0.4)',
                }}
              />
              <span style={{ fontWeight: 500 }}>Correlator Engine Online</span>
            </div>
          )}
        </nav>

        {/* Tab Views */}
        {activeTab === 'dashboard' && (
          <Dashboard
            incidents={incidents}
            selectedIncident={selectedIncident}
            onSelectIncident={handleSelectIncident}
            allSignals={signals}
            jiraTicketsCount={jiraTickets.length}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'details' && (
          <IncidentDetails
            incident={selectedIncident}
            allSignals={signals}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'graph' && (
          <EvidenceGraph
            incident={selectedIncident}
            graphData={graphData}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'review' && (
          <TicketReview
            incident={selectedIncident}
            onTicketPublished={handleTicketPublished}
            jiraTickets={jiraTickets}
            onNavigate={setActiveTab}
          />
        )}
      </main>
    </div>
  );
}
