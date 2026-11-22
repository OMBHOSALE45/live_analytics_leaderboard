import React, { useState } from 'react';
import SvgDefs from '../components/SvgDefs';

export default function RefereePanel({
  teams,
  pendingReviews,
  allEvents,
  matchInfo,
  connected,
  onAddKill,
  onUndoLastKill,
  onResetMatch,
  onConfirmReview,
  onRejectReview,
  onReassignKill
}) {
  const [killerTeam, setKillerTeam] = useState(teams[0]?.id || 'lyon');
  const [victimTeam, setVictimTeam] = useState(teams[1]?.id || 'onic');
  const [weapon, setWeapon] = useState('SCAR');
  const [reassignModalEvent, setReassignModalEvent] = useState(null);
  const [selectedNewKiller, setSelectedNewKiller] = useState('');

  const weapons = ['AWM', 'M1887', 'SCAR', 'MP40', 'GROZA', 'WOODPECKER', 'GRENADE', 'PLAYZONE'];

  const handleSubmitManualKill = (e) => {
    e.preventDefault();
    if (!killerTeam || !victimTeam) return;
    onAddKill(killerTeam, victimTeam, weapon);
  };

  const handleConfirmReassign = () => {
    if (reassignModalEvent && selectedNewKiller) {
      onReassignKill(reassignModalEvent.id, selectedNewKiller);
      setReassignModalEvent(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#080511] text-white p-4 font-rajdhani selection:bg-purple-600">
      <SvgDefs />

      {/* Header Bar */}
      <header className="flex flex-wrap items-center justify-between gap-4 p-3 bg-[#130926] border border-purple-800/60 rounded mb-4 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-amber-400 animate-pulse"></div>
          <div>
            <h1 className="font-esports font-black text-2xl uppercase tracking-wider text-amber-400 leading-none">
              REFEREE VERIFICATION & AUDIT CONSOLE
            </h1>
            <p className="text-xs text-purple-300 font-semibold mt-0.5">
              Human-in-the-Loop Safety Net • 10–30s Broadcast Delay Window
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs">
          {/* Socket.IO / Server Status Indicator */}
          <div className="flex items-center gap-1.5 px-3 py-1 bg-[#1c0f38] border border-purple-700/50 rounded">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-500 animate-ping'}`}></span>
            <span className="font-mono font-bold">
              {connected ? 'LIVE ENGINE CONNECTED' : 'OFFLINE (LOCAL BUFFER)'}
            </span>
          </div>

          {/* Match Telemetry */}
          <div className="flex items-center gap-2 font-mono font-bold bg-black/40 px-3 py-1 rounded border border-purple-900">
            <span className="text-cyan-400">{matchInfo.map}</span>
            <span>•</span>
            <span className="text-amber-300">TOTAL KILLS: {matchInfo.totalKills}</span>
            <span>•</span>
            <span className="text-emerald-400">SQUADS ALIVE: {matchInfo.squadsAlive}/12</span>
          </div>
        </div>
      </header>

      {/* Main Grid: Left = Queue & Actions, Right = Event Audit Log */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column (7 cols): Pending Queue & Manual Controls */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          {/* Pending Review Queue (<85% Confidence) */}
          <div className="bg-[#120824] border border-amber-500/40 rounded p-4 shadow-lg relative overflow-hidden">
            <div className="flex items-center justify-between border-b border-purple-900 pb-2 mb-3">
              <div className="flex items-center gap-2">
                <span className="text-amber-400 font-black text-lg">⚠️</span>
                <h2 className="font-esports font-black text-xl uppercase tracking-wider text-amber-300">
                  PENDING OCR VERIFICATION QUEUE ({pendingReviews.length})
                </h2>
              </div>
              <span className="text-xs text-gray-400">
                Confidence &lt; 85% • Awaiting 1-Click Referee Decision
              </span>
            </div>

            {pendingReviews.length === 0 ? (
              <div className="py-8 text-center text-gray-500 text-sm">
                ✅ No pending reviews. All OCR detections confirmed with ≥ 85% confidence.
              </div>
            ) : (
              <div className="space-y-3">
                {pendingReviews.map((rev) => (
                  <div 
                    key={rev.id}
                    className="p-3 bg-[#1c0f38] border border-amber-500/50 rounded flex flex-wrap items-center justify-between gap-3 animate-fadeIn"
                  >
                    <div className="flex items-center gap-3">
                      {/* Thumbnail Placeholder */}
                      <div className="w-16 h-10 bg-black/60 border border-purple-800 rounded flex items-center justify-center text-[10px] text-gray-500 font-mono">
                        CROP
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-esports font-bold text-lg text-amber-300 uppercase">
                            {rev.killerTeamName || rev.killer_team_id}
                          </span>
                          <span className="text-gray-400 text-xs font-mono">eliminated</span>
                          <span className="font-esports font-bold text-lg text-white uppercase">
                            {rev.victimTeamName || rev.victim_team_id || 'UNKNOWN'}
                          </span>
                        </div>
                        <div className="text-xs text-gray-400 flex items-center gap-2 mt-0.5">
                          <span>Weapon: <strong className="text-gray-300">{rev.weapon}</strong></span>
                          <span>•</span>
                          <span>Confidence: <strong className="text-amber-400">{(rev.confidence * 100).toFixed(0)}%</strong></span>
                        </div>
                      </div>
                    </div>

                    {/* 1-Click Action Buttons */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onConfirmReview(rev.id)}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-xs uppercase rounded transition"
                      >
                        ✓ Confirm
                      </button>
                      <button
                        onClick={() => {
                          setReassignModalEvent(rev);
                          setSelectedNewKiller(rev.killer_team_id);
                        }}
                        className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white font-bold text-xs uppercase rounded transition"
                      >
                        ↺ Reassign
                      </button>
                      <button
                        onClick={() => onRejectReview(rev.id)}
                        className="px-3 py-1.5 bg-red-700 hover:bg-red-600 active:scale-95 text-white font-bold text-xs uppercase rounded transition"
                      >
                        ✕ Void
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Referee Action Bar */}
          <div className="bg-[#120824] border border-purple-900 rounded p-4 shadow-lg">
            <h2 className="font-esports font-black text-xl uppercase tracking-wider text-cyan-300 border-b border-purple-900 pb-2 mb-3">
              EMERGENCY BROADCAST OVERRIDES
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={onUndoLastKill}
                className="px-4 py-2 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 active:scale-95 text-white font-esports font-black uppercase text-sm rounded shadow transition flex items-center gap-2"
              >
                <span>↩</span> UNDO LAST ACTIVE KILL
              </button>

              <button
                onClick={() => {
                  if (window.confirm('Are you sure you want to reset all kills for this match?')) {
                    onResetMatch();
                  }
                }}
                className="px-4 py-2 bg-[#23123d] hover:bg-red-950 active:scale-95 text-red-400 hover:text-red-300 font-esports font-black uppercase text-sm border border-red-800/50 rounded transition"
              >
                ⚠ RESET MATCH TO ZERO
              </button>
            </div>
          </div>

          {/* Manual Kill Entry Form */}
          <div className="bg-[#120824] border border-purple-900 rounded p-4 shadow-lg">
            <h2 className="font-esports font-black text-xl uppercase tracking-wider text-purple-300 border-b border-purple-900 pb-2 mb-3">
              MANUAL ATTRIBUTION OVERRIDE
            </h2>
            <form onSubmit={handleSubmitManualKill} className="flex flex-wrap items-end gap-3 text-xs">
              <div className="flex-1 min-w-[140px]">
                <label className="block text-gray-400 font-bold uppercase mb-1">Killer Squad</label>
                <select
                  value={killerTeam}
                  onChange={(e) => setKillerTeam(e.target.value)}
                  className="w-full bg-[#1c0f38] border border-purple-700 rounded px-2.5 py-1.5 text-white font-bold"
                >
                  {teams.map(t => (
                    <option key={t.id} value={t.id}>{t.name} ({t.country})</option>
                  ))}
                </select>
              </div>

              <div className="flex-1 min-w-[140px]">
                <label className="block text-gray-400 font-bold uppercase mb-1">Victim Squad</label>
                <select
                  value={victimTeam}
                  onChange={(e) => setVictimTeam(e.target.value)}
                  className="w-full bg-[#1c0f38] border border-purple-700 rounded px-2.5 py-1.5 text-white font-bold"
                >
                  {teams.map(t => (
                    <option key={t.id} value={t.id}>{t.name} ({t.country})</option>
                  ))}
                </select>
              </div>

              <div className="w-28">
                <label className="block text-gray-400 font-bold uppercase mb-1">Weapon</label>
                <select
                  value={weapon}
                  onChange={(e) => setWeapon(e.target.value)}
                  className="w-full bg-[#1c0f38] border border-purple-700 rounded px-2.5 py-1.5 text-white font-bold font-mono"
                >
                  {weapons.map(w => (
                    <option key={w} value={w}>{w}</option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                className="px-4 py-2 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 active:scale-95 text-white font-esports font-black text-sm uppercase rounded shadow transition"
              >
                + COMMIT KILL
              </button>
            </form>
          </div>
        </div>

        {/* Right Column (5 cols): Immutable Event Audit Ledger */}
        <div className="lg:col-span-5 bg-[#120824] border border-purple-900 rounded p-4 shadow-lg flex flex-col">
          <div className="flex items-center justify-between border-b border-purple-900 pb-2 mb-3">
            <h2 className="font-esports font-black text-xl uppercase tracking-wider text-cyan-300">
              IMMUTABLE EVENT LEDGER (AUDIT TRAIL)
            </h2>
            <span className="text-xs text-gray-400 font-mono">
              Zero State Drift
            </span>
          </div>

          <div className="space-y-2 overflow-y-auto max-h-[580px] pr-1">
            {allEvents.length === 0 ? (
              <div className="text-center py-10 text-xs text-gray-500">
                No ledger events logged yet.
              </div>
            ) : (
              allEvents.map((ev) => (
                <div
                  key={ev.id}
                  className={`p-2.5 rounded border text-xs flex items-center justify-between gap-2 transition ${
                    ev.status === 'ACTIVE'
                      ? 'bg-[#180e30] border-purple-800/80 text-gray-200'
                      : ev.status === 'VOIDED'
                      ? 'bg-[#1a1424] border-red-900/60 text-gray-500 line-through'
                      : 'bg-[#241738] border-amber-600/60 text-amber-200'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-400 font-mono">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                    </span>
                    <div>
                      <span className="font-bold uppercase text-amber-300">
                        {ev.killerTeamName || ev.killer_team_id}
                      </span>
                      <span className="mx-1 text-gray-500">→</span>
                      <span className="font-bold uppercase text-white">
                        {ev.victimTeamName || ev.victim_team_id || 'ENV'}
                      </span>
                      <span className="text-[10px] text-gray-400 ml-1.5 font-mono">
                        [{ev.weapon}]
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                        ev.status === 'ACTIVE'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : ev.status === 'VOIDED'
                          ? 'bg-red-950 text-red-400 border border-red-800'
                          : 'bg-amber-950 text-amber-400 border border-amber-800'
                      }`}
                    >
                      {ev.status}
                    </span>

                    {ev.status === 'ACTIVE' && (
                      <button
                        onClick={() => onUndoLastKill(ev.id)}
                        className="text-gray-400 hover:text-red-400 text-xs px-1 font-bold"
                        title="Void this kill event"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Reassign Killer Modal */}
      {reassignModalEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm bg-[#160b2d] border border-cyan-400 rounded p-5 text-white">
            <h3 className="font-esports font-black text-2xl uppercase text-cyan-300 mb-3">
              REASSIGN KILLER SQUAD
            </h3>
            <p className="text-xs text-gray-300 mb-4">
              Select the true elimination squad to correct the ledger:
            </p>
            <select
              value={selectedNewKiller}
              onChange={(e) => setSelectedNewKiller(e.target.value)}
              className="w-full bg-[#1c0f38] border border-purple-700 rounded p-2 text-white font-bold mb-4"
            >
              {teams.map(t => (
                <option key={t.id} value={t.id}>{t.name} ({t.country})</option>
              ))}
            </select>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setReassignModalEvent(null)}
                className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold text-xs uppercase rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmReassign}
                className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-black font-esports font-black text-sm uppercase rounded shadow"
              >
                Confirm Reassign
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

