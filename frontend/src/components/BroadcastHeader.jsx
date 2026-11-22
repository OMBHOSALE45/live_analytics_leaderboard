import React from 'react';

export default function BroadcastHeader({
  autoSimActive,
  onToggleAutoSim,
  onSimulateKill,
  onReset,
  viewMode,
  onToggleViewMode,
  matchTime,
  totalKills,
  squadsAlive,
  currentView = 'director',
  onChangeView,
  connected = false,
  visionActive = false,
  teamsCount = 0
}) {
  return (
    <header 
      className="w-full max-w-7xl relative z-20 flex flex-wrap items-center justify-between gap-3 px-4 py-2 mb-2 bg-[#120926]/90 backdrop-blur-md border border-purple-500/30 shadow-[0_4px_24px_rgba(0,0,0,0.65)] hud-clip-left"
      data-purpose="broadcast-header"
    >
      {/* Left Side: FFWS Tournament Crest + Match State */}
      <div className="flex items-center gap-3.5 flex-wrap">
        {/* FFWS Golden Diamond Emblem Badge */}
        <div className="flex items-center gap-2.5 pr-3 border-r border-purple-800/60">
          <div className="w-8 h-8 relative flex items-center justify-center bg-gradient-to-br from-amber-400 via-amber-600 to-purple-900 rounded-sm shadow-[0_0_12px_rgba(246,195,59,0.4)] p-[1.5px]">
            <div className="w-full h-full bg-[#120726] flex items-center justify-center">
              <svg className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2L15 8L21 9L16.5 13.5L18 19.5L12 16L6 19.5L7.5 13.5L3 9L9 8L12 2Z" />
              </svg>
            </div>
          </div>
          <div className="flex flex-col">
            <span className="font-esports font-black text-amber-400 text-sm tracking-wider uppercase leading-none">
              FFWS 2025
            </span>
            <span className="font-rajdhani text-[10px] text-purple-300 font-bold tracking-widest leading-tight uppercase">
              WORLD SERIES
            </span>
          </div>
        </div>

        {/* Live Pulsing Tag */}
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-gradient-to-r from-red-600 to-rose-700 text-white text-[11px] font-esports font-black tracking-widest uppercase rounded-sm shadow-[0_0_10px_rgba(220,38,38,0.6)]">
          <span className="w-2 h-2 rounded-full bg-white animate-ping"></span>
          LIVE
        </span>

        {/* Top Indicator: Backend Vision-Engine Active & Streaming */}
        <div className={`inline-flex items-center gap-2 px-3 py-1 rounded border transition-all duration-300 ${
          visionActive
            ? 'bg-emerald-950/90 border-emerald-400 text-emerald-200 shadow-[0_0_16px_rgba(16,185,129,0.45)]'
            : connected
            ? 'bg-amber-950/70 border-amber-500/50 text-amber-300'
            : 'bg-red-950/60 border-red-500/40 text-red-300'
        }`}>
          <span className={`w-2.5 h-2.5 rounded-full ${
            visionActive 
              ? 'bg-emerald-400 animate-ping shadow-[0_0_8px_#34d399]' 
              : connected 
              ? 'bg-amber-400 animate-pulse' 
              : 'bg-red-500'
          }`} />
          <div className="flex flex-col">
            <span className="font-esports font-black text-xs tracking-wider uppercase leading-none">
              {visionActive ? 'VISION ENGINE: ACTIVE & STREAMING' : connected ? 'SERVER READY (AWAITING FEED)' : 'SERVER OFFLINE'}
            </span>
            {visionActive && (
              <span className="font-mono text-[9px] text-emerald-300 font-bold tracking-tight mt-0.5">
                {teamsCount} SQUADS DETECTED • LIVE SYNC
              </span>
            )}
          </div>
        </div>

        {/* Match Stage & Map Telemetry */}
        <div className="flex items-center gap-2 font-rajdhani text-xs tracking-wider uppercase font-bold text-gray-300">
          <span className="text-white font-extrabold tracking-widest">GRAND FINALS</span>
          <span className="text-purple-400">•</span>
          <span className="text-cyan-400 font-extrabold bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-500/30">
            MATCH 4 — BERMUDA
          </span>
        </div>

        {/* In-Game Match Telemetry Badges */}
        <div className="hidden xl:flex items-center gap-2 pl-2 text-[11px] font-rajdhani font-bold border-l border-purple-800/60">
          <span className="text-emerald-400 flex items-center gap-1 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            {squadsAlive}/12 SQUADS
          </span>
          <span className="text-amber-300 flex items-center gap-1 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-500/30">
            PHASE 3 CIRCLE
          </span>
          <span className="text-cyan-300 flex items-center gap-1 bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-500/30">
            KILLS: {totalKills}
          </span>
          <span className="text-purple-300 tracking-wider font-mono">
            ⏱ {matchTime}
          </span>
        </div>
      </div>

      {/* Center/Right: View Switcher (Director Desk / OBS Overlay / Referee) */}
      <div className="flex items-center gap-1.5 bg-[#0b0617] p-1 rounded border border-purple-900/60">
        <button
          onClick={() => onChangeView('director')}
          className={`px-2.5 py-1 text-xs font-esports font-bold uppercase rounded transition ${
            currentView === 'director'
              ? 'bg-gradient-to-r from-purple-700 to-indigo-600 text-white shadow'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          DIRECTOR DESK
        </button>
        <button
          onClick={() => onChangeView('overlay')}
          className={`px-2.5 py-1 text-xs font-esports font-bold uppercase rounded transition ${
            currentView === 'overlay'
              ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-black shadow font-black'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          OBS OVERLAY
        </button>
        <button
          onClick={() => onChangeView('referee')}
          className={`px-2.5 py-1 text-xs font-esports font-bold uppercase rounded transition ${
            currentView === 'referee'
              ? 'bg-gradient-to-r from-amber-600 to-amber-500 text-black shadow font-black'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          REFEREE PANEL
        </button>
      </div>

      {/* Right Side: Chamfered HUD Simulation Controls */}
      <div className="flex items-center gap-2 font-esports uppercase tracking-wider text-xs">
        {/* Toggle Companion Desk */}
        <button
          onClick={onToggleViewMode}
          className="relative hud-btn-skew px-3 py-1.5 bg-[#1a1133] hover:bg-[#251848] text-cyan-300 hover:text-cyan-200 font-black text-xs border border-cyan-500/40 transition duration-200"
          title="Toggle companion broadcast analytics desk"
        >
          <span className="inline-block hud-btn-unskew flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            {viewMode === 'full' ? 'HIDE DESK' : 'DESK VIEW'}
          </span>
        </button>

        {/* Simulate Kill Button */}
        <button 
          id="btn-sim-kill"
          onClick={onSimulateKill}
          className="relative hud-btn-skew group overflow-hidden px-3.5 py-1.5 bg-gradient-to-r from-purple-800 to-indigo-700 hover:from-purple-700 hover:to-indigo-600 active:scale-95 text-white font-black text-sm border-l-2 border-r-2 border-cyan-400/80 shadow-[0_0_10px_rgba(123,75,229,0.5)] transition duration-200"
        >
          <span className="inline-block hud-btn-unskew flex items-center gap-1.5">
            <span className="text-amber-400 font-black text-base">+</span> SIMULATE KILL
          </span>
        </button>

        {/* Auto Sim Toggle Button */}
        <button 
          id="btn-toggle-auto"
          onClick={onToggleAutoSim}
          className={`relative hud-btn-skew group px-3.5 py-1.5 text-white font-black text-sm border-l-2 border-r-2 active:scale-95 transition duration-200 ${
            autoSimActive 
              ? 'bg-gradient-to-r from-emerald-800 to-teal-700 hover:from-emerald-700 hover:to-teal-600 border-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.4)]'
              : 'bg-zinc-800 hover:bg-zinc-700 border-zinc-500 text-gray-300 shadow'
          }`}
        >
          <span className="inline-block hud-btn-unskew flex items-center gap-1">
            AUTO SIM: <span className={autoSimActive ? 'font-mono text-amber-300' : 'font-mono text-gray-400'}>
              {autoSimActive ? 'ON' : 'OFF'}
            </span>
          </span>
        </button>

        {/* Reset Button */}
        <button 
          id="btn-reset"
          onClick={onReset}
          className="relative hud-btn-skew px-3 py-1.5 bg-[#1f1438] hover:bg-[#2b1c4e] active:scale-95 text-gray-300 hover:text-white font-black text-sm border border-purple-600/50 transition duration-200"
        >
          <span className="inline-block hud-btn-unskew">
            RESET
          </span>
        </button>
      </div>
    </header>
  );
}
