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
    this.spectatorTeam = null;
    this.teamNameMap = {};
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
    this.spectatorTeam = null;
    return this.getState();
  }

  setTeamNameMap(teamNames) {
    if (!teamNames || typeof teamNames !== 'object') return this.getState();
    const next = {};
    for (const [k, v] of Object.entries(teamNames)) {
      const key = String(k).trim().toUpperCase();
      if (v && typeof v === 'object' && v.name) {
        next[key] = { name: String(v.name).trim(), tag: v.tag ? String(v.tag).trim().toUpperCase() : undefined };
      } else if (typeof v === 'string' && v.trim()) {
        next[key] = { name: v.trim() };
      }
    }
    this.teamNameMap = next;
    return this.getState();
  }

  _resolveTeamIdentity(colorName, streamId, fallbackName, fallbackTag) {
    const colKey = String(colorName || '').trim().toUpperCase();
    const scoped = streamId && streamId !== 'default' ? `${String(streamId).toUpperCase()}:${colKey}` : null;
    const entry = (scoped && this.teamNameMap[scoped]) || this.teamNameMap[colKey];
    if (entry) {
      return {
        name: entry.name,
        clanTag: entry.tag || fallbackTag
      };
    }
    return {
      name: fallbackName,
      clanTag: fallbackTag
    };
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

    const resolved = this._resolveTeamIdentity(
      colorName,
      streamId,
      rawTeam.name || `TEAM ${rawTeam.colorName || idx + 1}`,
      rawTeam.clanTag || colorName.slice(0, 5).toUpperCase()
    );

    return {
      id: teamId,
      streamId,
      name: resolved.name,
      clanTag: resolved.clanTag,
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

  _normalizeName(str) {
    return String(str || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  _nameSimilarity(a, b) {
    const rawA = String(a || '').trim().toLowerCase();
    const rawB = String(b || '').trim().toLowerCase();
    if (!rawA || !rawB) return 0;
    if (rawA === rawB) return 1.0;

    const na = this._normalizeName(rawA);
    const nb = this._normalizeName(rawB);
    if (na && nb) {
      if (na === nb) return 0.98;
      if (na.length >= 3 && nb.length >= 3 && (na.includes(nb) || nb.includes(na))) {
        return Math.min(na.length, nb.length) / Math.max(na.length, nb.length) * 0.92;
      }
      // Bigram Dice coefficient for OCR noise tolerance
      if (na.length >= 2 && nb.length >= 2) {
        const bigramsA = new Map();
        for (let i = 0; i < na.length - 1; i++) {
          const bg = na.slice(i, i + 2);
          bigramsA.set(bg, (bigramsA.get(bg) || 0) + 1);
        }
        let overlap = 0;
        for (let i = 0; i < nb.length - 1; i++) {
          const bg = nb.slice(i, i + 2);
          const cnt = bigramsA.get(bg) || 0;
          if (cnt > 0) {
            overlap++;
            bigramsA.set(bg, cnt - 1);
          }
        }
        return (2 * overlap) / ((na.length - 1) + (nb.length - 1));
      }
    }

    // Fallback for non-ASCII / symbolic names (e.g. Devanagari/Bengali)
    const setA = new Set(rawA.replace(/\s+/g, ''));
    const setB = new Set(rawB.replace(/\s+/g, ''));
    let common = 0;
    for (const ch of setA) if (setB.has(ch)) common++;
    return (2 * common) / Math.max(1, setA.size + setB.size);
  }

  _matchTeamByPlayerNames(spectatedNames) {
    if (!Array.isArray(spectatedNames) || this.teams.length === 0) return null;
    const validQueries = spectatedNames
      .map((n, idx) => ({ idx, text: String(n || '').trim() }))
      .filter(q => q.text.length >= 2);
    if (validQueries.length === 0) return null;

    let bestTeam = null;
    let bestScore = 0;

    for (const team of this.teams) {
      const roster = Array.isArray(team.players) ? team.players : [];
      if (roster.length === 0) continue;

      let totalScore = 0;
      let strongHits = 0;
      for (const q of validQueries) {
        let bestPlayerScore = 0;
        for (let j = 0; j < roster.length; j++) {
          let sim = this._nameSimilarity(q.text, roster[j].name);
          if (j === q.idx && sim > 0.35) sim = Math.min(1.0, sim + 0.08);
          if (sim > bestPlayerScore) bestPlayerScore = sim;
        }
        if (bestPlayerScore >= 0.55) strongHits++;
        totalScore += bestPlayerScore;
      }

      const avgScore = totalScore / validQueries.length;
      if ((strongHits >= 1 && avgScore >= 0.45) || avgScore >= 0.58) {
        if (avgScore > bestScore) {
          bestScore = avgScore;
          bestTeam = team;
        }
      }
    }

    if (!bestTeam) return null;

    // Mark matched team in leaderboard and return a clean spectatorTeam snapshot
    for (const t of this.teams) {
      t.isSpectated = (t.id === bestTeam.id);
    }
    return {
      ...bestTeam,
      isSpectated: true,
      matchConfidence: Math.round(bestScore * 100) / 100
    };
  }

  syncScoreboard(payload) {
    if (!payload) {
      return this.getState();
    }

    const streamId = (payload.streamId && String(payload.streamId).trim()) || 'default';
    const nowMs = Date.now();
    const nowIso = new Date(nowMs).toISOString();

    // Fast-path for sub-millisecond spectator HP / knocked / yellow-eye / player-names lookup
    if (payload.hpOnly && (payload.spectatorHp || payload.spectatorTeam || Array.isArray(payload.spectatedPlayerNames))) {
      this.matchId = payload.matchId || this.matchId;
      this.status = 'LIVE';
      this.lastSyncTime = nowIso;
      if (payload.spectatorHp) {
        this.spectatorHp = payload.spectatorHp;
      }
      if (Array.isArray(payload.spectatedPlayerNames) && payload.spectatedPlayerNames.length > 0) {
        const matched = this._matchTeamByPlayerNames(payload.spectatedPlayerNames);
        if (matched) {
          this.spectatorTeam = matched;
        }
      }
      if (payload.spectatorTeam) {
        const mappedEyeTeam = this._mapTeam(payload.spectatorTeam, 0, streamId);
        // If we already have richer roster kills from the 12-team engine, keep matched name/tag consistency
        this.spectatorTeam = mappedEyeTeam;
      }
      const existingBucket = this.streams.get(streamId);
      if (existingBucket) {
        existingBucket.lastSync = nowIso;
        existingBucket.lastSyncMs = nowMs;
        if (payload.spectatorHp) existingBucket.spectatorHp = payload.spectatorHp;
      }
      return this.getState();
    }

    if (!Array.isArray(payload.teams)) {
      return this.getState();
    }

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
        spectatorTeam: this.spectatorTeam,
        stats: {
          totalKills: this.totalKills,
          squadsAlive: this.squadsAlive,
          totalSquads: this.teams.length,
          totalPlayersAlive: this.totalPlayersAlive
        }
      },
      leaderboard: this.teams,
      spectatorHp: this.spectatorHp,
      spectatorTeam: this.spectatorTeam,
      killFeed: [],
      pendingReviews: []
    };
  }
}

