import React from 'react';
import SvgDefs from '../components/SvgDefs';
import LeaderboardCard from '../components/LeaderboardCard';

export default function ObsOverlay({ teams, onTeamClick, flashTeamId }) {
  // Sort teams deterministically: highest elims first, then alive, then defaultRank
  const sortedTeams = [...teams].sort((a, b) => {
    if (b.elims !== a.elims) return b.elims - a.elims;
    if (b.alive !== a.alive) return b.alive - a.alive;
    return a.defaultRank - b.defaultRank;
  });

  return (
    <div 
      className="w-screen h-screen overflow-hidden flex items-start justify-start p-6 bg-transparent"
      style={{ background: 'transparent' }}
    >
      <SvgDefs />

      {/* Broadcast Overlay Card */}
      <div className="animate-fadeIn">
        <LeaderboardCard
          teams={sortedTeams}
          onTeamClick={onTeamClick}
          flashTeamId={flashTeamId}
        />
      </div>
    </div>
  );
}

