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
import WebhookModal from './components/WebhookModal';
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
  const [isWebhookModalOpen, setIsWebhookModalOpen] = useState(false);
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

      if (h.status === 'fulfilled') setHealth(h.value);
      if (sList.status === 'fulfilled') setSignals(sList.value);
      if (jList.status === 'fulfilled') setJiraTickets(jList.value);

      if (incList.status === 'fulfilled') {
        const loadedIncidents = incList.value || [];
        setIncidents(loadedIncidents);

        // Keep or select first incident
        if (loadedIncidents.length > 0) {
          setSelectedIncident((prev) => {
            if (prev) {
              const matched = loadedIncidents.find((i) => i.id === prev.id);
              return matched || loadedIncidents[0];
            }
            return loadedIncidents[0];
          });
        }
      }
    } catch (err) {
      console.error('Failed to load initial data:', err);
    }
  };

  useEffect(() => {
    loadData();
    // Poll health periodically every 15s
    const interval = setInterval(loadData, 15000);
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

  // Trigger full demo pipeline
  const handleRunDemo = async () => {
    setIsRunningDemo(true);
    try {
      const res = await api.runDemo();
      await loadData();
      showToast(
        `Demo executed: ${res.signals_ingested} signals ingested, ${res.incidents_created} incidents validated!`
      );
    } catch (err) {
      console.error('Demo run error:', err);
      showToast(`Error running demo: ${err.message}`);
    } finally {
      setIsRunningDemo(false);
    }
  };

  // Handle selecting an incident
  const handleSelectIncident = (inc) => {
    setSelectedIncident(inc);
    setActiveTab('details');
  };

  // Handle Jira ticket published
  const handleTicketPublished = (ticket) => {
    setJiraTickets((prev) => [ticket, ...prev.filter((t) => t.id !== ticket.id)]);
    showToast(`Published to Jira: ${ticket.id} (${ticket.title})`);
  };

  const tabs = [
    { id: 'dashboard', label: '1. Dashboard', icon: LayoutDashboard },
    { id: 'details', label: '2. Incident & Gates', icon: ShieldAlert },
    { id: 'graph', label: '3. Evidence Graph', icon: Network },
    { id: 'review', label: '4. Ticket Review & Jira', icon: FileCheck },
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
        onOpenWebhook={() => setIsWebhookModalOpen(true)}
        onRefresh={loadData}
      />

      {/* Main KPI Stats Bar */}
      <StatsBar
        signalsCount={signals.length}
        incidents={incidents}
        jiraTicketsCount={jiraTickets.length}
      />

      {/* Main Content Area */}
      <main style={{ padding: '0 28px 40px 28px', flex: 1 }}>
        {/* Navigation Tabs */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '20px',
        }}>
          <div style={{ display: 'flex', gap: '4px' }}>
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '12px 20px',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: isActive ? '2px solid var(--cyan)' : '2px solid transparent',
                    color: isActive ? 'var(--cyan)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 600 : 500,
                    fontSize: '0.88rem',
                    cursor: 'pointer',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  <Icon size={16} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Active Incident Indicator Chip */}
          {selectedIncident && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Active Incident:</span>
              <span className="font-mono badge badge-cyan">
                {selectedIncident.id}
              </span>
              <span className="badge badge-purple">
                {(selectedIncident.services || []).join(', ')}
              </span>
            </div>
          )}
        </div>

        {/* Tab Views */}
        {activeTab === 'dashboard' && (
          <Dashboard
            incidents={incidents}
            selectedIncident={selectedIncident}
            onSelectIncident={handleSelectIncident}
            allSignals={signals}
          />
        )}

        {activeTab === 'details' && (
          <IncidentDetails
            incident={selectedIncident}
            allSignals={signals}
          />
        )}

        {activeTab === 'graph' && (
          <EvidenceGraph
            incident={selectedIncident}
            graphData={graphData}
          />
        )}

        {activeTab === 'review' && (
          <TicketReview
            incident={selectedIncident}
            onTicketPublished={handleTicketPublished}
            jiraTickets={jiraTickets}
          />
        )}
      </main>

      {/* Webhook Modal */}
      <WebhookModal
        isOpen={isWebhookModalOpen}
        onClose={() => setIsWebhookModalOpen(false)}
        onWebhookSuccess={() => {
          loadData();
          showToast('Webhook payload processed successfully!');
        }}
      />
    </div>
  );
}
