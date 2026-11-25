import { useState, useEffect, useRef, useCallback } from 'react';
import { initialTeams } from '../data/teamsData';

export function useLeaderboard() {
  const [teams, setTeams] = useState([]);
  const [killFeed, setKillFeed] = useState([]);
  const [pendingReviews, setPendingReviews] = useState([]);
  const [allEvents, setAllEvents] = useState([]);
  const [spectatorHp, setSpectatorHp] = useState(null);
  const [connected, setConnected] = useState(false);
  const [matchInfo, setMatchInfo] = useState({
    id: 'ffws-live-match',
    map: 'BERMUDA',
    status: 'WAITING_FOR_FEED',
    scoringRules: 'KILLS_ONLY',
    totalKills: 0,
    squadsAlive: 0
  });

  const wsRef = useRef(null);

  // Helper to map backend team format to frontend UI format
  const mapServerTeams = useCallback((serverTeams) => {
    return serverTeams.map((st, idx) => ({
      id: st.id,
      name: st.name,
      country: st.country || 'Global',
      flag: st.flag || 'flag-global',
      logo: st.logo || 'logo-generic',
      color: st.color || '#00E5FF',
      colorName: st.colorName || 'CYAN',
      elims: st.elims ?? st.kills ?? 0,
      kills: st.kills ?? st.elims ?? 0,
      defaultRank: st.default_rank || st.rank || idx + 1,
      rank: st.rank || idx + 1,
      alive: st.alive ?? (st.players ? st.players.filter(p => p.alive !== false).length : 0),
      totalPlayers: st.totalPlayers || (st.players ? st.players.length : 4),
      damage: st.damage ?? 0,
      hp: typeof st.hp === 'number' ? st.hp : 100,
      isSpectated: Boolean(st.isSpectated),
      players: (st.players || []).map((p, pIdx) => ({
        slot: p.slot || pIdx + 1,
        name: p.name || `Player_${pIdx + 1}`,
        kills: p.kills || 0,
        alive: p.alive !== false,
        hp: typeof p.hp === 'number' ? p.hp : (p.alive !== false ? 100 : 0),
        hpState: p.hpState || p.hp_state || (p.alive !== false ? 'ALIVE' : 'DEAD')
      }))
    }));
  }, []);

  // Sync state from server update
  const applyServerState = useCallback((data) => {
    if (!data) return;

    if (Array.isArray(data.leaderboard)) {
      setTeams(mapServerTeams(data.leaderboard));
    }

    if (data.spectatorHp) {
      setSpectatorHp(data.spectatorHp);
    } else if (data.match?.spectatorHp) {
      setSpectatorHp(data.match.spectatorHp);
    }

    if (Array.isArray(data.killFeed)) {
      setKillFeed(data.killFeed.map(k => ({
        id: k.id,
        time: k.timestamp ? new Date(k.timestamp).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }) : '14:28',
        teamName: k.teamName || k.killer_team_id,
        teamLogo: k.teamLogo || `logo-${k.killer_team_id}`,
        pts: 1,
        weapon: k.weapon || 'SCAR',
        status: k.status
      })));
    }

    if (Array.isArray(data.pendingReviews)) {
      setPendingReviews(data.pendingReviews);
    }

    if (Array.isArray(data.allEvents)) {
      setAllEvents(data.allEvents);
    }

    if (data.match) {
      setMatchInfo(prev => ({
        ...prev,
        id: data.match.id,
        map: data.match.map,
        status: data.match.status,
        visionEngineActive: Boolean(data.match.visionEngineActive),
        totalKills: data.match.stats?.totalKills ?? prev.totalKills,
        squadsAlive: data.match.stats?.squadsAlive ?? prev.squadsAlive
      }));
    }
  }, [mapServerTeams]);

  // Connect via WebSocket with SSE & REST polling fallback
  useEffect(() => {
    let ws;
    let sse;
    let reconnectTimer;
    let pollInterval;

    // Instant REST poll on mount & continuous 800ms heartbeat with 3-tier fallback
    const pollServer = async () => {
      let stateApplied = false;

      // Tier 1: Try relative /api/match
      try {
        const res = await fetch('/api/match');
        if (res.ok) {
          const data = await res.json();
          if (data && (data.leaderboard || data.match)) {
            applyServerState(data);
            setConnected(true);
            stateApplied = true;
          }
        }
      } catch (err) {}

      // Tier 2: Try direct Port 3001 if running on Vite :5173
      if (!stateApplied && window.location.port !== '3001') {
        try {
          const host = window.location.hostname || 'localhost';
          const directRes = await fetch(`http://${host}:3001/api/match`);
          if (directRes.ok) {
            const data = await directRes.json();
            if (data && (data.leaderboard || data.match)) {
              applyServerState(data);
              setConnected(true);
              stateApplied = true;
            }
          }
        } catch (err) {}
      }

      // Tier 3: Zero-fail static file fallback to /live_state.json
      if (!stateApplied) {
        try {
          const fileRes = await fetch(`/live_state.json?t=${Date.now()}`);
          if (fileRes.ok) {
            const data = await fileRes.json();
            if (data && (data.leaderboard || data.match)) {
              applyServerState(data);
              setConnected(true);
              stateApplied = true;
            }
          }
        } catch (err) {}
      }
    };

    pollServer();
    pollInterval = setInterval(pollServer, 800);

    const connectWebSocket = () => {
      try {
        const wsUrl = `ws://${window.location.hostname || 'localhost'}:3001`;
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'init' || msg.type === 'leaderboard:update') {
              applyServerState(msg.data);
            }
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        ws.onclose = () => {
          // Reconnect after 3s
          reconnectTimer = setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        connectSSE();
      }
    };

    const connectSSE = () => {
      try {
        sse = new EventSource('/api/stream');
        sse.onopen = () => setConnected(true);
        sse.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'init' || msg.type === 'leaderboard:update') {
              applyServerState(msg.data);
            }
          } catch (err) {}
        };
        sse.onerror = () => {
          sse.close();
        };
      } catch (e) {}
    };

    connectWebSocket();

    return () => {
      if (ws) ws.close();
      if (sse) sse.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [applyServerState]);

  // Send Action to Backend (or fallback to local state if offline)
  const sendAction = useCallback((action, payload = {}) => {
    if (connected && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, payload }));
      return;
    }

    // Try REST endpoint if WS not open
    fetch('/api/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(() => {});

    // Local simulation fallback
    if (action === 'kill:add') {
      setTeams(prevTeams => {
        const next = prevTeams.map(t => {
          if (t.id === payload.killerTeamId) {
            return { ...t, elims: t.elims + 1, damage: t.damage + 150 };
          }
          if (t.id === payload.victimTeamId) {
            return { ...t, alive: Math.max(0, t.alive - 1) };
          }
          return t;
        });

        const scoring = next.find(t => t.id === payload.killerTeamId);
        if (scoring) {
          setKillFeed(prev => [
            {
              id: Date.now().toString(),
              time: '14:28',
              teamName: scoring.name,
              teamLogo: scoring.logo,
              pts: 1,
              weapon: payload.weapon || 'SCAR',
              status: 'ACTIVE'
            },
            ...prev.slice(0, 20)
          ]);
        }

        return next;
      });
    } else if (action === 'kill:undo') {
      setTeams(prev => prev.map((t, idx) => ({ ...t, elims: Math.max(0, t.elims - (idx === 0 ? 1 : 0)) })));
    } else if (action === 'match:reset') {
      setTeams(initialTeams);
      setKillFeed([]);
    }
  }, [connected]);

  const addKill = useCallback((killerTeamId, victimTeamId, weapon = 'SCAR') => {
    sendAction('kill:add', { killerTeamId, victimTeamId, weapon });
  }, [sendAction]);

  const voidKill = useCallback((eventId) => {
    sendAction('kill:void', { eventId });
  }, [sendAction]);

  const undoLastKill = useCallback(() => {
    sendAction('kill:undo', {});
  }, [sendAction]);

  const reassignKill = useCallback((eventId, newKillerTeamId) => {
    sendAction('kill:reassign', { eventId, newKillerTeamId });
  }, [sendAction]);

  const confirmReview = useCallback((eventId) => {
    sendAction('review:confirm', { eventId });
  }, [sendAction]);

  const rejectReview = useCallback((eventId) => {
    sendAction('review:reject', { eventId });
  }, [sendAction]);

  const resetMatch = useCallback(() => {
    sendAction('match:reset', {});
  }, [sendAction]);

  return {
    teams,
    killFeed,
    pendingReviews,
    allEvents,
    spectatorHp,
    matchInfo,
    connected,
    addKill,
    voidKill,
    undoLastKill,
    reassignKill,
    confirmReview,
    rejectReview,
    resetMatch
  };
}

