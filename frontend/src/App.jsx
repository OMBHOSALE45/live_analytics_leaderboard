import React, { useState, useEffect, useRef } from 'react';
import SvgDefs from './components/SvgDefs';
import BroadcastHeader from './components/BroadcastHeader';
import LeaderboardCard from './components/LeaderboardCard';
import LiveSpectatorHealthCard from './components/LiveSpectatorHealthCard';
import KillFeedPanel from './components/KillFeedPanel';
import SquadDetailsModal from './components/SquadDetailsModal';
import BroadcastFooter from './components/BroadcastFooter';
import ObsOverlay from './pages/ObsOverlay';
import RefereePanel from './pages/RefereePanel';
import { useLeaderboard } from './hooks/useLeaderboard';

export default function App() {
  const {
    teams,
    killFeed,
    pendingReviews,
    allEvents,
    spectatorHp,
    matchInfo,
    connected,
    addKill,
    undoLastKill,
    reassignKill,
    confirmReview,
    rejectReview,
    resetMatch
  } = useLeaderboard();

  // Route state: 'director' | 'overlay' | 'referee'
  const [currentView, setCurrentView] = useState(() => {
    const hash = window.location.hash.toLowerCase();
    const path = window.location.pathname.toLowerCase();
    if (hash.includes('overlay') || path.includes('overlay')) return 'overlay';
    if (hash.includes('referee') || path.includes('referee')) return 'referee';
    return 'director';
  });

  const [autoSimActive, setAutoSimActive] = useState(false);
  const [flashTeamId, setFlashTeamId] = useState(null);
  const [viewMode, setViewMode] = useState('full'); // 'full' or 'overlay'
  const [selectedSquad, setSelectedSquad] = useState(null);
  const [matchSeconds, setMatchSeconds] = useState(868); // 14:28 in seconds

  const flashTimerRef = useRef(null);

  // Sync hash with route
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.toLowerCase();
      if (hash.includes('overlay')) setCurrentView('overlay');
      else if (hash.includes('referee')) setCurrentView('referee');
      else setCurrentView('director');
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleChangeView = (view) => {
    setCurrentView(view);
    window.location.hash = view === 'director' ? '' : view;
  };

  // Format match timer: 14:28
  const formatTime = (secs) => {
    const mins = Math.floor(secs / 60);
    const s = secs % 60;
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Match clock ticker
  useEffect(() => {
    const clockInterval = setInterval(() => {
      setMatchSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(clockInterval);
  }, []);

  // Award kill through hook
  const handleAddKill = (killerTeamId, victimTeamId = null, weapon = 'SCAR') => {
    if (!victimTeamId) {
      // Choose random other team as victim
      const otherTeams = teams.filter(t => t.id !== killerTeamId);
      victimTeamId = otherTeams[Math.floor(Math.random() * otherTeams.length)]?.id;
    }

    addKill(killerTeamId, victimTeamId, weapon);

    // Score glow flash
    setFlashTeamId(killerTeamId);
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => {
      setFlashTeamId(null);
    }, 750);
  };

  // Auto simulation loop
  useEffect(() => {
    if (!autoSimActive) return;

    const interval = setInterval(() => {
      const randIdx = Math.floor(Math.random() * teams.length);
      const chosenTeam = teams[randIdx];
      if (chosenTeam) {
        handleAddKill(chosenTeam.id);
      }
    }, 3600);

    return () => clearInterval(interval);
  }, [autoSimActive, teams]);

  // Deterministically sorted teams
  const sortedTeams = [...teams].sort((a, b) => {
    if (b.elims !== a.elims) return b.elims - a.elims;
    if (b.alive !== a.alive) return b.alive - a.alive;
    return a.defaultRank - b.defaultRank;
  });

  const totalKills = teams.reduce((acc, t) => acc + (t.elims || 0), 0);
  const squadsAlive = teams.filter((t) => (t.alive ?? 4) > 0).length;

  // View: OBS Transparent Overlay Mode
  if (currentView === 'overlay') {
    return (
      <div className="relative">
        <ObsOverlay
          teams={sortedTeams}
          onTeamClick={handleAddKill}
          flashTeamId={flashTeamId}
        />
        {/* Floating switcher for preview convenience */}
        <div className="fixed bottom-3 right-3 opacity-30 hover:opacity-100 transition-opacity z-50">
          <button
            onClick={() => handleChangeView('director')}
            className="px-3 py-1 bg-black/80 text-cyan-300 font-mono text-xs rounded border border-cyan-500/50"
          >
            ← Back to Director Desk
          </button>
        </div>
      </div>
    );
  }

  // View: Referee Panel Mode
  if (currentView === 'referee') {
    return (
      <div className="relative">
        <div className="fixed top-2 right-4 z-50">
          <button
            onClick={() => handleChangeView('director')}
            className="px-3 py-1 bg-purple-900/80 hover:bg-purple-800 text-white font-rajdhani font-bold text-xs rounded border border-purple-500/50"
          >
            ← Back to Director Desk
          </button>
        </div>
        <RefereePanel
          teams={teams}
          pendingReviews={pendingReviews}
          allEvents={allEvents}
          matchInfo={matchInfo}
          connected={connected}
          onAddKill={handleAddKill}
          onUndoLastKill={undoLastKill}
          onResetMatch={resetMatch}
          onConfirmReview={confirmReview}
          onRejectReview={rejectReview}
          onReassignKill={reassignKill}
        />
      </div>
    );
  }

  // View: Main Director Desk (Default)
  return (
    <div className="min-h-screen flex flex-col justify-between items-center py-2 px-3 ff-bg-mesh relative overflow-x-hidden scanlines selection:bg-purple-600 selection:text-white">
      {/* SVG Definitions for Flags and Team Vector Logos */}
      <SvgDefs />

      {/* Cinematic Tournament Stage Ambience / Watermark FX */}
      <div className="absolute inset-0 tactical-grid pointer-events-none opacity-60"></div>
      
      {/* Glowing stage lights & cyber spotlights */}
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -top-28 -right-28 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -bottom-24 left-1/2 -translate-x-1/2 w-[700px] h-48 bg-purple-600/15 rounded-full blur-3xl pointer-events-none"></div>

      {/* Tactical Geometric Angles Watermark in background */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.035] select-none">
        <svg className="w-[880px] h-[880px]" fill="none" viewBox="0 0 500 500" xmlns="http://www.w3.org/2000/svg">
          <polygon points="250,20 460,130 460,370 250,480 40,370 40,130" stroke="#5BE2FF" strokeWidth="2.5" />
          <polygon points="250,60 420,150 420,350 250,440 80,350 80,150" stroke="#F6C33B" strokeWidth="1.5" />
          <path d="M120 250 H380 M250 120 V380" stroke="#ffffff" strokeWidth="1" />
          <circle cx="250" cy="250" r="160" stroke="#7B4BE5" strokeDasharray="8 6" strokeWidth="1.8" />
          <circle cx="250" cy="250" r="80" stroke="#5BE2FF" strokeWidth="1.2" />
        </svg>
      </div>

      {/* Broadcast Header HUD with View Switcher */}
      <BroadcastHeader
        autoSimActive={autoSimActive}
        onToggleAutoSim={() => setAutoSimActive((prev) => !prev)}
        onSimulateKill={() => {
          const randIdx = Math.floor(Math.random() * teams.length);
          handleAddKill(teams[randIdx].id);
        }}
        onReset={resetMatch}
        viewMode={viewMode}
        onToggleViewMode={() => setViewMode((prev) => (prev === 'full' ? 'overlay' : 'full'))}
        matchTime={formatTime(matchSeconds)}
        totalKills={totalKills}
        squadsAlive={squadsAlive}
        currentView={currentView}
        onChangeView={handleChangeView}
        connected={connected}
        visionActive={Boolean(matchInfo.visionEngineActive)}
        teamsCount={teams.length}
      />

      {/* Main Desktop Broadcast Stage */}
      <div className="w-full max-w-7xl flex-1 flex flex-col md:flex-row items-center md:items-start justify-center gap-8 lg:gap-14 my-4 px-2 relative z-10">
        {/* The Free Fire Live Leaderboard Overlay Card */}
        <div className="w-full max-w-[460px] flex flex-col items-center flex-shrink-0">
          <LeaderboardCard
            teams={sortedTeams}
            onTeamClick={handleAddKill}
            flashTeamId={flashTeamId}
            onSelectSquad={(squad) => setSelectedSquad(squad)}
          />

          {/* Live Spectator Health Telemetry HUD */}
          <LiveSpectatorHealthCard
            spectatorHp={spectatorHp}
            fallbackTeam={sortedTeams[0]}
          />
        </div>

        {/* Desktop Broadcast Companion / Telemetry Desk (Toggled by viewMode) */}
        {viewMode === 'full' && (
          <div className="w-full max-w-[450px] flex flex-col animate-fadeIn flex-shrink-0">
            <KillFeedPanel
              teams={sortedTeams}
              killFeed={killFeed}
              onTeamClick={handleAddKill}
              matchTime={formatTime(matchSeconds)}
              onSelectSquad={(squad) => setSelectedSquad(squad)}
            />
          </div>
        )}
      </div>

      {/* Broadcast Footer Info */}
      <BroadcastFooter />

      {/* Squad Details Inspection Modal */}
      {selectedSquad && (
        <SquadDetailsModal
          squad={selectedSquad}
          onClose={() => setSelectedSquad(null)}
          onAddKill={(id) => {
            handleAddKill(id);
            setSelectedSquad((prev) => prev ? { ...prev, elims: prev.elims + 1 } : null);
          }}
        />
      )}
    </div>
  );
}
