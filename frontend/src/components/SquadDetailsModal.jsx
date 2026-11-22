import React from 'react';

export default function SquadDetailsModal({ squad, onClose, onAddKill }) {
  if (!squad) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="w-full max-w-md bg-[#160b2d] border border-cyan-400/50 rounded-sm shadow-[0_0_30px_rgba(91,226,255,0.25)] p-5 relative font-rajdhani text-white hud-clip-left">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-gray-400 hover:text-white font-mono font-bold text-lg w-7 h-7 flex items-center justify-center rounded bg-purple-950/60 border border-purple-800"
        >
          ✕
        </button>

        {/* Squad Header */}
        <div className="flex items-center gap-3.5 border-b border-purple-800/60 pb-3 mb-4">
          <svg className="w-12 h-12 flex-shrink-0" viewBox="0 0 32 32">
            <use href={`#${squad.logo}`} />
          </svg>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-esports font-black text-3xl uppercase tracking-wide leading-none text-white">
                {squad.name}
              </h3>
              <svg className="w-6 h-4 shadow flex-shrink-0" viewBox="0 0 28 18">
                <use href={`#${squad.flag}`} />
              </svg>
            </div>
            <div className="text-xs text-purple-300 font-bold uppercase tracking-wider mt-0.5">
              Representing {squad.country} • Free Fire World Series
            </div>
          </div>
        </div>

        {/* Squad Performance Matrix */}
        <div className="grid grid-cols-3 gap-2.5 mb-4 text-center">
          <div className="bg-[#1e103d] border border-purple-900 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase font-bold">Total Elims</div>
            <div className="font-esports font-black text-2xl text-amber-400">{squad.elims}</div>
          </div>
          <div className="bg-[#1e103d] border border-purple-900 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase font-bold">Squad Alive</div>
            <div className="font-esports font-black text-2xl text-emerald-400">{squad.alive} / 4</div>
          </div>
          <div className="bg-[#1e103d] border border-purple-900 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase font-bold">Damage Dealt</div>
            <div className="font-esports font-black text-2xl text-cyan-400">{squad.damage}</div>
          </div>
        </div>

        {/* Roster List */}
        <div className="mb-4">
          <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">
            Active Lineup Roster
          </div>
          <div className="grid grid-cols-2 gap-2">
            {squad.players.map((player, idx) => {
              const pName = typeof player === 'string' ? player : (player.name || `Player_${idx+1}`);
              const pKills = typeof player === 'object' && player.kills !== undefined ? player.kills : 0;
              const pAlive = typeof player === 'object' && player.alive !== undefined ? player.alive : true;

              return (
                <div 
                  key={idx}
                  className={`flex items-center justify-between px-2.5 py-1.5 bg-[#1f113f] border ${pAlive ? 'border-purple-900/60' : 'border-red-950/40 opacity-50'} rounded text-xs`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${pAlive ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-gray-500'}`}></span>
                    <span className={`font-bold ${pAlive ? 'text-gray-100' : 'text-gray-400 line-through'}`}>{pName}</span>
                  </div>
                  <span className="text-[11px] text-amber-300 font-mono font-bold">
                    {pKills} {pKills === 1 ? 'kill' : 'kills'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Action Button */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-purple-900/60">
          <button
            onClick={() => {
              onAddKill(squad.id);
            }}
            className="px-4 py-1.5 bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-black font-esports font-black uppercase text-sm rounded shadow transition active:scale-95 flex items-center gap-1"
          >
            <span>+</span> Award Kill (+1 ELIM)
          </button>
        </div>
      </div>
    </div>
  );
}

