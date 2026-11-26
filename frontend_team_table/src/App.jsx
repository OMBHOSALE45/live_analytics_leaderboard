import { useEffect, useState } from 'react';

const DEFAULT_SQUAD = {
  clanTag: 'TAG',
  fullName: 'TEAM APEX GAMING',
  logoText: 'apex',
  flagColors: ['#FF9933', '#138808'],
  chakra: true,
  players: [
    { seat: 1, name: 'TAG.SAHIL7', kills: 1, weapon: 'fist', status: 'none', alive: true, hp: 100 },
    { seat: 2, name: 'TAG.KDGOD', kills: 1, weapon: 'sniper', status: 'none', alive: true, hp: 100 },
    { seat: 3, name: 'TAG.SHOT017', kills: 0, weapon: 'ar', status: 'parachute', alive: true, hp: 100 },
    { seat: 4, name: 'TAG.LOUIS', kills: 1, weapon: 'ar', status: 'car', alive: true, hp: 100 },
  ],
};

function WeaponIcon({ weapon }) {
  if (weapon === 'fist') {
    return (
      <div className="w-6 h-6 flex items-center justify-center text-gray-200" title="Melee / Fist">
        <svg className="w-4 h-4 fill-white filter drop-shadow" viewBox="0 0 24 24">
          <path d="M19.5 7.5a2.5 2.5 0 0 0-2.5-2.5c-.3 0-.6.1-.8.2-.5-.7-1.3-1.2-2.2-1.2-.5 0-.9.1-1.3.4-.5-.9-1.4-1.4-2.5-1.4-1.4 0-2.5 1-2.7 2.3-.3-.1-.7-.1-1-.1-2.2 0-4 1.8-4 4 0 .9.3 1.8.8 2.5L2 14.5V20c0 1.1.9 2 2 2h8.5c2.4 0 4.6-1.3 5.8-3.4l2.7-4.7c.3-.5.5-1.1.5-1.7V7.5z" />
        </svg>
      </div>
    );
  }
  if (weapon === 'sniper') {
    return (
      <div className="flex items-center" title="Sniper Rifle (AWM / Kar98k)">
        <svg className="w-10 h-3 fill-white filter drop-shadow" viewBox="0 0 64 20">
          <path d="M2 14h10l3-4h18v2h-12l-2 3h-8v3H1l1-4zm24-6h12v2H26V8zm14 2h14v2H40v-2zm15 0h8v1h-8v-1zM28 12h14l4 4h-6l-3-2h-8l-1-2z" />
        </svg>
        <span className="w-2.5 h-1.5 bg-yellow-300 rounded-full blur-[1px] ml-0.5 muzzle-glow" />
      </div>
    );
  }
  return (
    <div className="w-9 h-4 flex items-center justify-center" title="Assault Rifle">
      <svg className="w-8 h-3.5 fill-white" viewBox="0 0 48 18">
        <path d="M2 12h7l2-4h18v2h-8l-2 4h-5v3H2v-5zm22-3h16v2H24V9zm16 1h6v1h-6v-1zM27 12h8l2 5h-4l-2-3h-4v-2z" />
      </svg>
    </div>
  );
}

function StatusBadge({ status }) {
  if (status === 'parachute') {
    return (
      <div className="text-cyan-300 pl-1" title="In Parachute / Redeploying">
        <svg className="w-4 h-4 fill-current filter drop-shadow-[0_0_4px_#38bdf8]" viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12c0 .4.04.79.1 1.18l3.14-1.57A6.978 6.978 0 0 1 12 4c2.87 0 5.37 1.73 6.48 4.22l3.23 1.62C21.89 8.27 17.43 2 12 2zm-1 11h2v3h-2v-3zm0 5h2v4h-2v-4zM6 13.5l3.5 3.5 1.4-1.4-3.5-3.5L6 13.5zm12 0l-1.4-1.4-3.5 3.5 1.4 1.4L18 13.5z" />
        </svg>
      </div>
    );
  }
  if (status === 'car') {
    return (
      <div className="text-gray-100 pl-1" title="Driver in Vehicle">
        <svg className="w-3.5 h-4.5 fill-current filter drop-shadow" viewBox="0 0 24 30">
          <path d="M5 2c-1.1 0-2 .9-2 2v2h2V4h14v2h2V4c0-1.1-.9-2-2-2H5zm-2 7h2v6H3V9zm16 0h2v6h-2V9zM5 7h14c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2v3c0 .5-.4 1-1 1h-2c-.5 0-1-.5-1-1v-2H9v2c0 .5-.5 1-1 1H6c-.6 0-1-.5-1-1v-3c-1.1 0-2-.9-2-2V9c0-1.1.9-2 2-2zm2 4v2h10v-2H7zm0 5v2h10v-2H7z" />
        </svg>
      </div>
    );
  }
  return null;
}

function mapLiveTeamToSquad(team) {
  const players = (team.players || []).slice(0, 4).map((p, idx) => ({
    seat: p.slot || idx + 1,
    name: p.name || `Player_${idx + 1}`,
    kills: p.kills || 0,
    weapon: idx === 0 ? 'fist' : idx === 1 ? 'sniper' : 'ar',
    status: 'none',
    alive: p.alive !== false,
    hp: typeof p.hp === 'number' ? p.hp : (p.alive !== false ? 100 : 0),
  }));

  const rawName = (team.name || 'TEAM').trim();
  const tag = rawName.split(/\s+/)[0].slice(0, 5).toUpperCase();

  return {
    clanTag: tag,
    fullName: rawName.toUpperCase(),
    logoText: tag.toLowerCase(),
    flagColors: ['#FF9933', '#138808'],
    chakra: true,
    players,
  };
}

export default function App() {
  const [squad, setSquad] = useState(DEFAULT_SQUAD);

  useEffect(() => {
    let ws;
    let cancelled = false;

    const applyPayload = (data) => {
      if (cancelled || !data || !Array.isArray(data.leaderboard) || data.leaderboard.length === 0) {
        return;
      }
      const target = data.leaderboard.find((t) => t.isSpectated) || data.leaderboard[0];
      if (target) {
        setSquad(mapLiveTeamToSquad(target));
      }
    };

    const pollMatch = async () => {
      try {
        const host = window.location.hostname || 'localhost';
        const res = await fetch(`http://${host}:3001/api/match`);
        if (res.ok) {
          applyPayload(await res.json());
        }
      } catch {
        // Keep default Stitch squad when backend is offline
      }
    };

    pollMatch();

    try {
      const host = window.location.hostname || 'localhost';
      ws = new WebSocket(`ws://${host}:3001`);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'init' || msg.type === 'leaderboard:update') {
            applyPayload(msg.data);
          }
        } catch {
          // Ignore malformed frames
        }
      };
    } catch {
      // Ignore WebSocket errors when offline
    }

    return () => {
      cancelled = true;
      if (ws) ws.close();
    };
  }, []);

  const totalElims = squad.players.reduce((sum, p) => sum + (p.kills || 0), 0);

  return (
    <>
      <div className="fixed top-0 left-1/4 w-96 h-96 bg-purple-600/10 rounded-full blur-[140px] pointer-events-none -z-10" />
      <div className="fixed bottom-0 right-1/4 w-[500px] h-[500px] bg-indigo-900/20 rounded-full blur-[180px] pointer-events-none -z-10" />

      <main className="min-h-screen w-full flex items-center justify-center p-4 relative z-10">
        <div
          className="w-full max-w-[420px] transition-all duration-300 select-none drop-shadow-2xl"
          data-purpose="esports-squad-card"
          id="ffws-squad-overlay"
        >
          <div className="rounded-lg overflow-hidden border-2 border-purple-700/60 shadow-[0_10px_35px_rgba(0,0,0,0.8)] bg-[#12092a]">
            {/* Squad Header */}
            <div className="relative ffws-header-bg px-3 py-2 flex items-center justify-between border-b-2 border-purple-500/40 overflow-hidden">
              <div className="absolute -right-8 -top-8 w-44 h-24 bg-gradient-to-l from-cyan-400/25 via-purple-300/30 to-transparent transform -rotate-12 pointer-events-none blur-sm" />
              <div className="absolute left-20 top-0 bottom-0 w-24 bg-gradient-to-r from-purple-400/20 to-transparent pointer-events-none transform skew-x-12" />

              <div className="flex items-center space-x-3 z-10">
                <div className="relative">
                  <div className="w-12 h-12 rounded-full p-[2px] bg-gradient-to-tr from-cyan-400 via-purple-500 to-ffws-gold shadow-md flex items-center justify-center">
                    <div
                      className="w-full h-full rounded-full bg-[#1b193d] flex items-center justify-center overflow-hidden border border-purple-400/50"
                      id="teamLogoHolder"
                    >
                      <div className="flex flex-col items-center justify-center leading-none text-center">
                        <span className="font-chakra font-black text-cyan-300 text-[11px] tracking-tighter">
                          {squad.logoText}
                        </span>
                        <div className="w-3 h-[2px] bg-ffws-gold rounded mt-0.5" />
                      </div>
                    </div>
                  </div>

                  {/* Country Flag Badge */}
                  <div className="absolute -top-1 -right-3 z-20 shadow-md border border-white/40 rounded-[2px] overflow-hidden w-6 h-4 bg-white flex flex-col justify-between">
                    <div className="w-full h-1/3" style={{ backgroundColor: squad.flagColors[0] }} />
                    <div className="w-full h-1/3 bg-white flex items-center justify-center relative">
                      {squad.chakra && (
                        <div className="w-1.5 h-1.5 rounded-full border-[1px] border-[#000080] flex items-center justify-center">
                          <div className="w-0.5 h-0.5 bg-[#000080] rounded-full" />
                        </div>
                      )}
                    </div>
                    <div className="w-full h-1/3" style={{ backgroundColor: squad.flagColors[1] }} />
                  </div>
                </div>

                <div className="pl-2">
                  <h2 className="font-chakra font-black text-2xl tracking-wider text-white uppercase drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
                    {squad.clanTag}
                  </h2>
                  <p className="font-chakra text-[10px] text-purple-300 font-semibold tracking-widest -mt-1 uppercase">
                    {squad.fullName}
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2 z-10 pr-2">
                <span className="font-chakra font-bold text-sm tracking-widest text-purple-200 uppercase">
                  Elim
                </span>
                <span className="font-tall-num text-4xl text-white font-bold tracking-tight drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)] min-w-[24px] text-right">
                  {totalElims}
                </span>
              </div>
            </div>

            {/* Squad Roster Rows */}
            <div className="flex flex-col divide-y divide-purple-900/60 font-hud">
              {squad.players.map((player, idx) => {
                const isAlt = idx % 2 === 1;
                const isKnocked = !player.alive || player.hp <= 0;
                const hpPct = Math.max(0, Math.min(100, player.hp ?? 100));

                return (
                  <div
                    key={player.seat}
                    className={`${isAlt ? 'ffws-player-row-alt' : 'ffws-player-row'} ${isKnocked ? 'knocked-active border-l-4 border-red-500 opacity-75' : ''
                      } flex items-center justify-between px-3 py-2 transition-all duration-300 hover:bg-purple-900/40 relative`}
                  >
                    <div
                      className="absolute bottom-0 left-0 h-[2px] bg-gradient-to-r from-emerald-400 via-emerald-500 to-transparent transition-all duration-300"
                      style={{ width: `${hpPct}%` }}
                    />

                    <div className="flex items-center space-x-3">
                      <div className="w-6 h-6 rounded bg-[#0d071e] border border-purple-700/50 flex items-center justify-center text-white font-chakra font-bold text-sm shadow-inner">
                        {player.seat}
                      </div>
                      <span className="font-chakra font-bold text-sm text-white tracking-wide uppercase drop-shadow">
                        {player.name}
                      </span>
                    </div>

                    <div className="flex items-center space-x-3">
                      <WeaponIcon weapon={player.weapon} />
                      <span className="font-tall-num text-2xl font-bold text-white tracking-normal min-w-[16px] text-right">
                        {player.kills}
                      </span>
                      <StatusBadge status={player.status} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
