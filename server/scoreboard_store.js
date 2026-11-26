/**
 * In-Memory Live Scoreboard Store
 * Manages dynamically discovered teams across one or more vision streams,
 * merges them into unified rankings by total kills, and broadcasts state.
 */
export class ScoreboardStore {
  constructor() {
    this.matchId = 'ffws-live-match';
    this.map = 'BERMUDA';
    this.status = 'WAITING_FOR_FEED';
    this.teams = []; // Unified ranked teams merged across active streams
    this.streams = new Map(); // streamId -> { teams, lastSync, lastSyncMs, spectatorHp }
    this.history = []; // History of sync updates
    this.lastSyncTime = null;
    this.totalKills = 0;
    this.squadsAlive = 0;
    this.totalPlayersAlive = 0;
    this.spectatorHp = null;
  }

  reset() {
    this.teams = [];
    this.streams.clear();
    this.history = [];
    this.status = 'WAITING_FOR_FEED';
    this.lastSyncTime = null;
    this.totalKills = 0;
    this.squadsAlive = 0;
    this.totalPlayersAlive = 0;
    this.spectatorHp = null;
    return this.getState();
  }

  _mapTeam(rawTeam, idx, streamId) {
    const players = Array.isArray(rawTeam.players) ? rawTeam.players : [];
    const computedKills = rawTeam.kills !== undefined
      ? rawTeam.kills
      : players.reduce((sum, p) => sum + (p.kills || 0), 0);
    const computedAlive = rawTeam.alive !== undefined
      ? rawTeam.alive
      : players.filter(p => p.alive !== false).length;

    const mappedPlayers = players.map((p, pIdx) => {
      const isAlive = p.alive !== false;
      const playerHp = typeof p.hp === 'number' ? Math.round(p.hp * 10) / 10 : (isAlive ? 100 : 0);
      return {
        slot: p.slot || pIdx + 1,
        name: p.name || `Player_${pIdx + 1}`,
        kills: p.kills || 0,
        alive: isAlive,
        hp: playerHp,
        hpState: p.hp_state || p.state || (isAlive ? 'ALIVE' : 'DEAD'),
        color: p.color,
        hex: p.hex
      };
    });

    const teamAvgHp = rawTeam.hp !== undefined
      ? rawTeam.hp
      : (mappedPlayers.length > 0
          ? Math.round(mappedPlayers.reduce((s, p) => s + p.hp, 0) / mappedPlayers.length)
          : 100);

    const colorName = rawTeam.colorName || 'CYAN';
    const rawId = rawTeam.id || `team-${colorName.toLowerCase().replace(/\s+/g, '-') || `team_${idx}`}`;
    const needsStreamPrefix = streamId !== 'default'
      && (!rawTeam.id || rawId.startsWith('team-'))
      && !rawId.startsWith(`${streamId}-`);
    const teamId = needsStreamPrefix ? `${streamId}-${rawId}` : rawId;

    return {
      id: teamId,
      streamId,
      name: rawTeam.name || `TEAM ${rawTeam.colorName || idx + 1}`,
      color: rawTeam.color || '#00E5FF',
      colorName,
      kills: computedKills,
      elims: computedKills, // For compatibility with existing UI
      alive: computedAlive,
      totalPlayers: mappedPlayers.length || 4,
      hp: teamAvgHp,
      isSpectated: Boolean(rawTeam.isSpectated),
      players: mappedPlayers
    };
  }

  syncScoreboard(payload) {
    if (!payload || !Array.isArray(payload.teams)) {
      return this.getState();
    }

    const streamId = (payload.streamId && String(payload.streamId).trim()) || 'default';
    const nowMs = Date.now();
    const nowIso = new Date(nowMs).toISOString();

    this.matchId = payload.matchId || this.matchId;
    this.status = 'LIVE';
    this.lastSyncTime = nowIso;
    if (payload.spectatorHp) {
      this.spectatorHp = payload.spectatorHp;
    }

    const streamTeams = payload.teams.map((rawTeam, idx) => this._mapTeam(rawTeam, idx, streamId));
    this.streams.set(streamId, {
      teams: streamTeams,
      lastSync: nowIso,
      lastSyncMs: nowMs,
      spectatorHp: payload.spectatorHp || null
    });

    // Merge teams across all active stream buckets (freshest bucket wins on explicit ID match)
    const orderedBuckets = Array.from(this.streams.values()).sort((a, b) => a.lastSyncMs - b.lastSyncMs);
    const mergedById = new Map();
    for (const bucket of orderedBuckets) {
      for (const team of bucket.teams) {
        mergedById.set(team.id, team);
      }
    }
    const updatedTeams = Array.from(mergedById.values());

    // Rank collectively: 1st by kills DESC, 2nd by alive DESC, 3rd by colorName/id
    updatedTeams.sort((a, b) => {
      if (b.kills !== a.kills) return b.kills - a.kills;
      if (b.alive !== a.alive) return b.alive - a.alive;
      const colorCmp = a.colorName.localeCompare(b.colorName);
      return colorCmp !== 0 ? colorCmp : a.id.localeCompare(b.id);
    });

    // Assign unified ranking numbers
    updatedTeams.forEach((t, i) => {
      t.rank = i + 1;
      t.default_rank = i + 1;
    });

    this.teams = updatedTeams;
    this.totalKills = this.teams.reduce((sum, t) => sum + t.kills, 0);
    this.squadsAlive = this.teams.filter(t => t.alive > 0).length;
    this.totalPlayersAlive = this.teams.reduce((sum, t) => sum + t.alive, 0);

    return this.getState();
  }

  getState() {
    const nowMs = Date.now();
    const isVisionActive = Boolean(this.lastSyncTime && (nowMs - new Date(this.lastSyncTime).getTime() < 4000));
    const streamStatus = {};
    for (const [id, bucket] of this.streams.entries()) {
      streamStatus[id] = {
        lastSync: bucket.lastSync,
        active: nowMs - bucket.lastSyncMs < 4000,
        teamsCount: bucket.teams.length
      };
    }

    return {
      match: {
        id: this.matchId,
        map: this.map,
        status: this.status,
        lastSync: this.lastSyncTime,
        visionEngineActive: isVisionActive,
        streams: streamStatus,
        spectatorHp: this.spectatorHp,
        stats: {
          totalKills: this.totalKills,
          squadsAlive: this.squadsAlive,
          totalSquads: this.teams.length,
          totalPlayersAlive: this.totalPlayersAlive
        }
      },
      leaderboard: this.teams,
      spectatorHp: this.spectatorHp,
      killFeed: [],
      pendingReviews: []
    };
  }
}

