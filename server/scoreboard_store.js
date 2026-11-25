/**
 * In-Memory Live Scoreboard Store
 * Manages dynamically discovered teams from video stream,
 * calculates team rankings by total kills, and broadcasts state.
 */
export class ScoreboardStore {
  constructor() {
    this.matchId = 'ffws-live-match';
    this.map = 'BERMUDA';
    this.status = 'WAITING_FOR_FEED';
    this.teams = []; // Dynamically discovered teams
    this.history = []; // History of sync updates
    this.lastSyncTime = null;
    this.totalKills = 0;
    this.squadsAlive = 0;
    this.totalPlayersAlive = 0;
    this.spectatorHp = null;
  }

  reset() {
    this.teams = [];
    this.history = [];
    this.status = 'WAITING_FOR_FEED';
    this.lastSyncTime = null;
    this.totalKills = 0;
    this.squadsAlive = 0;
    this.totalPlayersAlive = 0;
    this.spectatorHp = null;
    return this.getState();
  }

  syncScoreboard(payload) {
    if (!payload || !Array.isArray(payload.teams)) {
      return this.getState();
    }

    this.matchId = payload.matchId || this.matchId;
    this.status = 'LIVE';
    this.lastSyncTime = new Date().toISOString();
    if (payload.spectatorHp) {
      this.spectatorHp = payload.spectatorHp;
    }

    // Map incoming teams
    const updatedTeams = payload.teams.map((rawTeam, idx) => {
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

      return {
        id: rawTeam.id || `team-${(rawTeam.colorName || `team_${idx}`).toLowerCase()}`,
        name: rawTeam.name || `TEAM ${rawTeam.colorName || idx + 1}`,
        color: rawTeam.color || '#00E5FF',
        colorName: rawTeam.colorName || 'CYAN',
        kills: computedKills,
        elims: computedKills, // For compatibility with existing UI
        alive: computedAlive,
        totalPlayers: mappedPlayers.length || 4,
        hp: teamAvgHp,
        isSpectated: Boolean(rawTeam.isSpectated),
        players: mappedPlayers
      };
    });

    // Rank teams: 1st by kills DESC, 2nd by alive DESC, 3rd by colorName
    updatedTeams.sort((a, b) => {
      if (b.kills !== a.kills) return b.kills - a.kills;
      if (b.alive !== a.alive) return b.alive - a.alive;
      return a.colorName.localeCompare(b.colorName);
    });

    // Assign ranking numbers
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
    const isVisionActive = Boolean(this.lastSyncTime && (Date.now() - new Date(this.lastSyncTime).getTime() < 4000));
    return {
      match: {
        id: this.matchId,
        map: this.map,
        status: this.status,
        lastSync: this.lastSyncTime,
        visionEngineActive: isVisionActive,
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

