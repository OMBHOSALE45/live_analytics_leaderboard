import React, { useState, useEffect } from 'react';
import './App.css';
import SvgDefs from './components/SvgDefs';
import LeaderboardCard from './components/LeaderboardCard';
import { useLeaderboard } from './hooks/useLeaderboard';

export default function App() {
  const { teams } = useLeaderboard();
  const [flashTeamId, setFlashTeamId] = useState(null);

  // Deterministically sorted teams: highest elims first, then alive, then defaultRank
  const sortedTeams = [...teams].sort((a, b) => {
    if (b.elims !== a.elims) return b.elims - a.elims;
    if (b.alive !== a.alive) return b.alive - a.alive;
    return a.defaultRank - b.defaultRank;
  });

  return (
    <div className="min-h-screen w-full bg-[#0a0517] text-white flex flex-col items-center justify-start py-6 px-4 select-none relative">
      {/* SVG Definitions for Flags and Team Vector Logos */}
      <SvgDefs />

      {/* Main Tournament Stage Card */}
      <div className="w-full max-w-[460px] flex flex-col items-center">
        {/* Tournament Name Header */}
        <div className="w-full bg-[#14082e] border border-purple-500/50 rounded-lg px-4 py-3 flex items-center justify-between shadow-2xl mb-3">
          <div className="flex items-center gap-3">
            {/* FFWS Golden Crest Emblem */}
            <div className="w-9 h-9 relative flex items-center justify-center bg-gradient-to-br from-amber-400 via-amber-500 to-purple-900 rounded p-[1.5px] shadow-[0_0_14px_rgba(246,195,59,0.5)]">
              <div className="w-full h-full bg-[#120726] flex items-center justify-center rounded-[2px]">
                <svg className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2L15 8L21 9L16.5 13.5L18 19.5L12 16L6 19.5L7.5 13.5L3 9L9 8L12 2Z" />
                </svg>
              </div>
            </div>
            <div className="flex flex-col">
              <span className="font-esports font-black text-amber-400 text-lg tracking-wider uppercase leading-none">
                FREE FIRE WORLD SERIES
              </span>
              <span className="font-rajdhani text-xs text-purple-200 font-bold tracking-widest leading-tight uppercase mt-0.5">
                FFWS 2025 • GRAND FINALS
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-red-600 text-white text-[11px] font-esports font-black tracking-widest uppercase rounded shadow-[0_0_10px_rgba(220,38,38,0.7)]">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
            LIVE
          </div>
        </div>

        {/* Live Game Standings Leaderboard Card */}
        <LeaderboardCard
          teams={sortedTeams}
          flashTeamId={flashTeamId}
        />
      </div>
    </div>
  );
}
