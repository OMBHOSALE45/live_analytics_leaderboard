import React from 'react';
import { getRankSuffix } from '../data/teamsData';

export default function LeaderboardCard({
  teams,
  onTeamClick,
  flashTeamId,
  onSelectSquad
}) {
  const ROW_HEIGHT = 56; // 48px row + 8px gap for clean spacing

  // Authentic Free Fire 4 slanted player survival status bars (////) with Live Health Telemetry
  const renderAliveBars = (team) => {
    const bars = [];
    const totalBars = 4;
    const players = Array.isArray(team.players) ? team.players : [];
    const aliveCount = typeof team.alive === 'number' ? team.alive : 4;

    for (let i = 0; i < totalBars; i++) {
      const p = players[i];
      const isPlayerAlive = p !== undefined ? Boolean(p.alive) : i < aliveCount;
      const playerHp = p && typeof p.hp === 'number' ? p.hp : (isPlayerAlive ? 100 : 0);

      bars.push(
        <div
          key={i}
          className="relative flex flex-col justify-end w-2.5 h-6 bg-gray-950/80 border border-purple-800/60 rounded-xs overflow-hidden transform -skew-x-[14deg]"
          title={`Squad Member ${i + 1} (${p?.name || 'Player'}): ${playerHp.toFixed(1)}% HP [${isPlayerAlive ? 'ALIVE' : 'ELIMINATED'}]`}
        >
          <div
            className="w-full transition-all duration-300 rounded-xs"
            style={{
              height: `${Math.max(0, Math.min(100, playerHp))}%`,
              backgroundColor: !isPlayerAlive ? '#3a3a3a' : playerHp > 50 ? '#00e676' : playerHp > 25 ? '#ffeb3b' : '#ff1744',
              boxShadow: isPlayerAlive && playerHp > 0 ? `0 0 5px ${playerHp > 50 ? '#00e676' : playerHp > 25 ? '#ffeb3b' : '#ff1744'}` : 'none'
            }}
          />
        </div>
      );
    }
    return bars;
  };

  return (
    <main
      className="w-full max-w-[460px] flex flex-col drop-shadow-2xl relative z-10 flex-shrink-0"
      data-purpose="leaderboard-overlay"
    >
      {/* Leaderboard Slanted Headers matching FFWS official graphic */}
      <div
        className="w-full flex items-end justify-between px-1 mb-2 relative z-10"
        data-purpose="table-header-tabs"
      >
        {/* GAME STANDINGS Slanted Blue Polygon */}
        <div className="relative bg-gradient-to-r from-[#59c9ed] to-[#7ee7ff] text-[#0d2238] font-black italic tracking-tighter px-7 py-1.5 header-poly transform -skew-x-[12deg] shadow-lg">
          <span className="inline-block transform skew-x-[12deg] text-xl font-esports uppercase font-black tracking-normal">
            GAME STANDINGS
          </span>
        </div>

        {/* ELIMS Slanted Small Cyan Notch Tab - Aligned directly above the right-hand elims & alive bars */}
        <div className="relative bg-gradient-to-r from-[#6ce8ff] to-[#54c7ec] text-[#0c2438] font-black italic px-4 py-1.5 elims-poly transform -skew-x-[14deg] shadow-lg flex items-center justify-center min-w-[96px] mr-1">
          <span className="inline-block transform skew-x-[14deg] text-base font-esports uppercase font-black tracking-wider text-center">
            ELIMS
          </span>
          {/* Speech chevron notch pointing down directly at elims */}
          <div className="elims-notch"></div>
        </div>
      </div>

      {/* Dynamic Rows Leaderboard with Animated Rank Re-ordering */}
      <section
        aria-label="Free Fire Live Standings"
        className="w-full select-none relative transition-all duration-300"
        data-purpose="team-rows-container"
        id="leaderboard-rows-container"
        style={{ height: `${Math.max(1, teams.length) * ROW_HEIGHT}px`, minHeight: '120px' }}
      >
        {teams.length === 0 ? (
          <div className="p-8 text-center bg-[#150a26]/90 border border-purple-500/30 rounded shadow-xl flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-cyan-300 font-esports text-lg tracking-wider">AWAITING VIDEO STREAM SCAN</span>
            <p className="text-xs text-purple-300/80 font-rajdhani">Start the video detector to auto-plot teams by color & live kills</p>
          </div>
        ) : (
          teams.map((team, rankIndex) => {
            const rank = team.rank || rankIndex + 1;
            const isFirst = rank === 1;
            const isFlashing = flashTeamId === team.id;
            const squadColor = team.color || '#00E5FF';

            return (
              <div
                key={team.id || `team-${rankIndex}`}
                id={`row-${team.id}`}
                className={`team-row flex items-stretch cursor-pointer group ${isFlashing ? 'flash-score' : ''}`}
                data-purpose={`team-row-${team.id}`}
                title={`Click to inspect squad ${team.name}`}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  height: '48px',
                  transform: `translateY(${rankIndex * ROW_HEIGHT}px)`,
                  transition: 'transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.3s ease',
                  zIndex: 20 - rankIndex
                }}
                onClick={() => {
                  if (onSelectSquad) onSelectSquad(team);
                  else if (onTeamClick) onTeamClick(team.id);
                }}
              >
                {/* Rank Parallelogram Badge */}
                <div
                  className={`rank-badge w-12 flex items-center justify-center font-black italic tracking-tighter text-lg skew-badge transition-all duration-300 ${isFirst
                    ? 'bg-gradient-to-br from-[#ffd84d] to-[#F6C33B] text-[#1b1202] shadow-[0_0_14px_rgba(246,195,59,0.55)] border-t border-amber-200/50'
                    : 'bg-gradient-to-br from-[#8d5fed] to-[#7B4BE5] text-white border-t border-purple-300/30'
                    }`}
                >
                  <span className="rank-text unskew font-esports font-black text-xl leading-none">
                    {getRankSuffix(rank)}
                  </span>
                </div>

                {/* Team Main Banner Body */}
                <div
                  className="flex-1 ml-1.5 px-3 py-2 bg-gradient-to-r from-[#211438] via-[#1a0e2e] to-[#120824] flex items-center justify-between border-y border-purple-900/60 shadow-md group-hover:border-purple-500/80 group-hover:from-[#2c194a] transition-colors duration-150 relative"
                  style={{ borderLeft: `4px solid ${squadColor}` }}
                >
                  {/* Left Info: Team Color Emblem & Name */}
                  <div className="flex items-center gap-2.5 min-w-0">
                    {/* Team Color Pill */}
                    <span
                      className="w-3.5 h-3.5 rounded-full flex-shrink-0 shadow-sm"
                      style={{
                        backgroundColor: squadColor,
                        boxShadow: `0 0 8px ${squadColor}`
                      }}
                    />

                    {/* Team Name */}
                    <span className="team-name text-white font-esports font-black text-2xl tracking-wide uppercase leading-none drop-shadow">
                      {team.name}
                    </span>

                    {/* Alive count pill */}
                    <span className="text-[14px] font-bold px-2 py-0.5 rounded-lg bg-purple-950/80 border border-purple-700/50 text-cyan-300 font-mono">
                      {team.alive ?? 4} ALIVE
                    </span>

                    {/* Team Live Health Pill (Vision Sync) */}
                    <div 
                      className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-black/60 border border-purple-800/50 shadow-sm"
                      title={`Live Squad HP: ${(team.hp ?? 100).toFixed(1)}%`}
                    >
                      <span className="text-[10px] font-mono font-bold text-gray-400">HP</span>
                      <div className="w-10 h-2 bg-gray-900 rounded-xs overflow-hidden p-[1px] border border-gray-700">
                        <div 
                          className="h-full rounded-xs transition-all duration-300"
                          style={{
                            width: `${Math.max(0, Math.min(100, team.hp ?? 100))}%`,
                            backgroundColor: (team.hp ?? 100) > 50 ? '#00e676' : (team.hp ?? 100) > 25 ? '#ffeb3b' : '#ff1744',
                            boxShadow: `0 0 4px ${(team.hp ?? 100) > 50 ? '#00e676' : (team.hp ?? 100) > 25 ? '#ffeb3b' : '#ff1744'}`
                          }}
                        />
                      </div>
                      <span 
                        className="text-[11px] font-mono font-bold"
                        style={{
                          color: (team.hp ?? 100) > 50 ? '#69f0ae' : (team.hp ?? 100) > 25 ? '#ffff8d' : '#ff5252'
                        }}
                      >
                        {Math.round(team.hp ?? 100)}%
                      </span>
                      {team.isSpectated && (
                        <span className="text-[9px] uppercase font-bold tracking-wider px-1 bg-cyan-950 border border-cyan-500/60 text-cyan-300 rounded animate-pulse">
                          LIVE
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right Info: Elims count & Survival Tally Bars (4 per squad) */}
                  <div className="flex items-center gap-2.5 flex-shrink-0">
                    {/* Numerical Elims */}
                    <span className="elims-count font-esports text-amber-300 font-black text-2xl w-8 text-center tracking-normal leading-none drop-shadow">
                      {team.elims ?? team.kills ?? 0}
                    </span>

                    {/* Slanted Survival Tally Bars (////) - full if alive, empty if dead */}
                    <div className="tally-bars flex items-center gap-1.5 pr-0.5">
                      {renderAliveBars(team)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </section>
    </main>
  );
}

