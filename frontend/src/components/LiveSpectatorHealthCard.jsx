import React from 'react';

export default function LiveSpectatorHealthCard({ spectatorHp, fallbackTeam }) {
  // Use spectatorHp if available, otherwise fallback to the first active team
  const squad = spectatorHp || (fallbackTeam ? {
    teamName: fallbackTeam.name,
    teamColor: fallbackTeam.color,
    avgHp: fallbackTeam.hp ?? 100,
    players: (fallbackTeam.players || []).map((p, i) => ({
      slot: p.slot || i + 1,
      name: p.name || `Player_${i + 1}`,
      hp: p.hp ?? (p.alive !== false ? 100 : 0),
      state: p.hpState || (p.alive !== false ? 'ALIVE' : 'DEAD')
    }))
  } : null);

  if (!squad) return null;

  const teamColor = squad.teamColor || '#00E5FF';
  const avgHp = Math.round(squad.avgHp ?? 100);

  return (
    <section 
      className="w-full max-w-[460px] bg-[#140a24]/95 border border-purple-800/70 rounded-sm shadow-xl p-3.5 backdrop-blur-md relative font-rajdhani text-white mt-3"
      data-purpose="live-spectator-health-card"
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-purple-800/60 pb-2 mb-2.5">
        <div className="flex items-center gap-2">
          {/* Pulsing indicator */}
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
          </span>
          <span className="font-esports font-black text-sm uppercase tracking-wider text-cyan-300">
            SPECTATOR SQUAD LIVE HEALTH
          </span>
        </div>

        {/* Squad Badge */}
        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/50 border border-purple-700/40">
          <span 
            className="w-2.5 h-2.5 rounded-full" 
            style={{ backgroundColor: teamColor, boxShadow: `0 0 6px ${teamColor}` }}
          />
          <span className="font-esports font-bold text-xs uppercase tracking-wide text-white">
            {squad.teamName}
          </span>
        </div>
      </div>

      {/* 4 Player Health Meters */}
      <div className="grid grid-cols-1 gap-2">
        {(squad.players || []).slice(0, 4).map((p, idx) => {
          const hp = typeof p.hp === 'number' ? Math.max(0, Math.min(100, p.hp)) : 100;
          const isDead = p.state === 'DEAD' || hp <= 1.0;
          const isKnocked = p.state === 'KNOCKED';
          
          let barColor = '#00e676';
          let glowColor = 'rgba(0, 230, 118, 0.4)';
          let badgeText = 'ALIVE';
          let badgeClass = 'bg-emerald-950 text-emerald-400 border-emerald-700/60';

          if (isDead) {
            barColor = '#424242';
            glowColor = 'none';
            badgeText = 'DEAD';
            badgeClass = 'bg-gray-900 text-gray-500 border-gray-700/40';
          } else if (isKnocked) {
            barColor = '#ff1744';
            glowColor = 'rgba(255, 23, 68, 0.5)';
            badgeText = 'KNOCKED';
            badgeClass = 'bg-red-950 text-red-400 border-red-700/60 animate-pulse';
          } else if (hp <= 25) {
            barColor = '#ff5252';
            glowColor = 'rgba(255, 82, 82, 0.4)';
          } else if (hp <= 50) {
            barColor = '#ffd600';
            glowColor = 'rgba(255, 214, 0, 0.4)';
          }

          return (
            <div 
              key={idx}
              className={`p-2 rounded bg-[#1c1033] border ${isDead ? 'border-gray-800 opacity-60' : 'border-purple-800/50'} transition-all duration-200`}
            >
              {/* Player Name, HP Number & State Badge */}
              <div className="flex items-center justify-between text-xs mb-1 font-bold">
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-400 font-mono text-[11px]">P{p.slot || idx + 1}</span>
                  <span className={`truncate max-w-[150px] ${isDead ? 'text-gray-500 line-through' : 'text-gray-100'}`}>
                    {p.name || `Player_${idx + 1}`}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span 
                    className="font-mono text-sm font-black"
                    style={{ color: isDead ? '#757575' : barColor }}
                  >
                    {hp.toFixed(1)}%
                  </span>
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded border ${badgeClass}`}>
                    {badgeText}
                  </span>
                </div>
              </div>

              {/* Smooth Animated Horizontal HP Bar */}
              <div className="w-full h-2.5 bg-black/70 rounded-xs overflow-hidden p-[1px] border border-purple-950">
                <div 
                  className="h-full rounded-xs transition-all duration-300 ease-out"
                  style={{
                    width: `${hp}%`,
                    backgroundColor: barColor,
                    boxShadow: glowColor !== 'none' ? `0 0 8px ${glowColor}` : 'none'
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Info */}
      <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-purple-900/40 text-[11px] text-gray-400 font-mono">
        <span>AI VISION CONTIGUOUS L-TO-R SYNC</span>
        <span className="text-emerald-400 font-bold">SQUAD AVG HP: {avgHp}%</span>
      </div>
    </section>
  );
}
