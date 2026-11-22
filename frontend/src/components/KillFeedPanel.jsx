import React from 'react';

export default function KillFeedPanel({
  teams,
  killEvents = [],
  killFeed = [],
  onTeamClick,
  matchTime,
  onSelectSquad
}) {
  const events = killEvents.length > 0 ? killEvents : killFeed;
  // Sort teams to find MVP / Kill Leader
  const mvpTeam = [...teams].sort((a, b) => b.elims - a.elims || b.damage - a.damage)[0];

  return (
    <aside 
      className="w-full max-w-[420px] flex flex-col gap-3 relative z-10 font-rajdhani"
      data-purpose="broadcast-companion-panel"
    >
      {/* Tournament MVP / Match Leader Card */}
      <div className="bg-[#140b28]/90 border border-amber-500/30 rounded p-3 backdrop-blur shadow-lg relative overflow-hidden">
        <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/10 rounded-full blur-xl pointer-events-none"></div>
        <div className="flex items-center justify-between border-b border-purple-900/60 pb-2 mb-2">
          <div className="flex items-center gap-1.5 text-xs uppercase font-extrabold text-amber-400 tracking-wider">
            <span>👑</span>
            <span>CURRENT KILL LEADER • MATCH MVP</span>
          </div>
          <span className="text-[11px] font-mono font-bold text-gray-400 bg-black/40 px-2 py-0.5 rounded">
            RANK #1
          </span>
        </div>

        {mvpTeam && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <svg className="w-9 h-9" viewBox="0 0 32 32">
                <use href={`#${mvpTeam.logo}`} />
              </svg>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-esports font-black text-2xl text-white tracking-wide uppercase leading-tight">
                    {mvpTeam.name}
                  </span>
                  <svg className="w-5 h-3.5 shadow" viewBox="0 0 28 18">
                    <use href={`#${mvpTeam.flag}`} />
                  </svg>
                </div>
                <div className="text-xs text-purple-300 font-semibold">
                  {mvpTeam.country} • {mvpTeam.alive}/4 Alive
                </div>
              </div>
            </div>

            <div className="text-right">
              <div className="text-3xl font-esports font-black text-amber-400 leading-none">
                {mvpTeam.elims} <span className="text-sm font-rajdhani text-gray-400 font-bold uppercase">Kills</span>
              </div>
              <div className="text-[11px] text-gray-400 font-medium">
                {mvpTeam.damage} DMG Dealt
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Live Kill Feed Broadcast Ticker */}
      <div className="bg-[#120824]/90 border border-purple-900/60 rounded p-3 backdrop-blur shadow-lg flex-1 flex flex-col">
        <div className="flex items-center justify-between border-b border-purple-900/50 pb-2 mb-2">
          <div className="flex items-center gap-2 text-xs uppercase font-extrabold text-cyan-400 tracking-wider">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <span>LIVE COMBAT FEED</span>
          </div>
          <span className="text-[11px] text-gray-400 font-mono">
            {events.length} Eliminations
          </span>
        </div>

        {/* Feed List */}
        <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
          {events.length === 0 ? (
            <div className="text-center py-6 text-xs text-gray-500 italic">
              Awaiting next elimination event...
            </div>
          ) : (
            events.slice(0, 8).map((event) => (
              <div 
                key={event.id}
                className="flex items-center justify-between px-2.5 py-1.5 bg-[#1a0f30]/80 border-l-2 border-amber-400 rounded-sm text-xs animate-fadeIn"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-purple-300 font-mono">
                    {event.time}
                  </span>
                  <div className="flex items-center gap-1 font-bold text-white">
                    <svg className="w-4 h-4" viewBox="0 0 32 32">
                      <use href={`#${event.teamLogo}`} />
                    </svg>
                    <span className="text-amber-300 uppercase">{event.teamName}</span>
                  </div>
                  <span className="text-gray-400 text-[11px]">secured kill</span>
                </div>
                <span className="text-emerald-400 font-extrabold text-[11px] font-mono">
                  +1 PTS
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Broadcaster Quick Kill Attribution Matrix */}
      <div className="bg-[#120824]/90 border border-purple-900/60 rounded p-3 backdrop-blur shadow-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs uppercase font-extrabold text-purple-300 tracking-wider">
            DIRECTOR HUD • SQUADS ATTRIBUTION
          </span>
          <span className="text-[10px] text-gray-400">Click to +1 kill</span>
        </div>

        <div className="grid grid-cols-4 gap-1.5">
          {teams.map((team) => (
            <button
              key={team.id}
              onClick={() => onTeamClick(team.id)}
              className="flex items-center justify-between px-2 py-1 bg-[#1a0f32] hover:bg-[#2e1952] active:scale-95 border border-purple-800/40 hover:border-cyan-400/60 rounded transition group"
              title={`Award +1 kill to ${team.name}`}
            >
              <div className="flex items-center gap-1">
                <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 32 32">
                  <use href={`#${team.logo}`} />
                </svg>
                <span className="font-esports font-bold text-white text-xs">
                  {team.name}
                </span>
              </div>
              <span className="text-[11px] font-mono font-bold text-amber-400">
                {team.elims}
              </span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

