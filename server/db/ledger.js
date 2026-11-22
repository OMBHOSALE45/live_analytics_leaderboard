import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export class KillLedger {
  constructor(dbPath = ':memory:') {
    this.dbPath = dbPath;
    this.db = new DatabaseSync(dbPath);
    this.initSchema();
  }

  initSchema() {
    const schemaPath = path.join(__dirname, 'schema.sql');
    if (fs.existsSync(schemaPath)) {
      const sql = fs.readFileSync(schemaPath, 'utf8');
      this.db.exec(sql);
    }
  }

  seedRoster(roster) {
    const matchId = roster.matchId || 'ffws-2025-gf-match-4';
    
    // Check if match already exists
    const existing = this.db.prepare('SELECT id FROM matches WHERE id = ?').get(matchId);
    if (existing) {
      return matchId;
    }

    const insertMatch = this.db.prepare(`
      INSERT INTO matches (id, map, scoring_rules, status)
      VALUES (?, ?, ?, 'LIVE')
    `);
    insertMatch.run(matchId, roster.map || 'BERMUDA', roster.scoringRules || 'KILLS_ONLY');

    const insertTeam = this.db.prepare(`
      INSERT INTO teams (id, match_id, name, tag, country, logo, flag, default_rank, alive_players, damage_dealt)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 4, 0)
    `);

    const insertPlayer = this.db.prepare(`
      INSERT INTO players (id, team_id, match_id, ign, normalized_skeleton, role, is_alive)
      VALUES (?, ?, ?, ?, ?, ?, 1)
    `);

    let rankIdx = 1;
    for (const team of roster.teams) {
      insertTeam.run(
        team.id,
        matchId,
        team.name,
        team.tag || team.name,
        team.country,
        team.logo,
        team.flag,
        rankIdx++
      );

      if (Array.isArray(team.players)) {
        for (const p of team.players) {
          insertPlayer.run(
            p.id || `${team.id}-${p.ign.toLowerCase()}`,
            team.id,
            matchId,
            p.ign,
            p.normalizedSkeleton || p.ign.toLowerCase().replace(/[^a-z0-9]/g, ''),
            p.role || 'Rusher'
          );
        }
      }
    }

    return matchId;
  }

  getActiveMatch() {
    const match = this.db.prepare(`
      SELECT * FROM matches WHERE status = 'LIVE' ORDER BY started_at DESC LIMIT 1
    `).get();

    if (!match) return null;

    const stats = this.getMatchStats(match.id);
    return {
      ...match,
      stats
    };
  }

  getMatchStats(matchId) {
    const totalKillsRow = this.db.prepare(`
      SELECT COUNT(*) as count FROM kill_events WHERE match_id = ? AND status = 'ACTIVE'
    `).get(matchId);

    const activeSquadsRow = this.db.prepare(`
      SELECT COUNT(*) as count FROM teams WHERE match_id = ? AND alive_players > 0
    `).get(matchId);

    const pendingRow = this.db.prepare(`
      SELECT COUNT(*) as count FROM kill_events WHERE match_id = ? AND status = 'PENDING_REVIEW'
    `).get(matchId);

    return {
      totalKills: totalKillsRow?.count || 0,
      squadsAlive: activeSquadsRow?.count || 0,
      pendingReviews: pendingRow?.count || 0
    };
  }

  // Immutable Kill Event Logging
  addKillEvent({
    matchId,
    killerTeamId,
    killerPlayerId = null,
    victimTeamId = null,
    victimPlayerId = null,
    weapon = 'UNKNOWN',
    confidence = 1.0,
    source = 'VISION_AI',
    cropPath = null,
    status = 'ACTIVE',
    matchTimeSec = 0,
    notes = null
  }) {
    // Edge case rule: prevent self-kill from inflating team's kills
    if (killerTeamId && victimTeamId && killerTeamId === victimTeamId) {
      status = 'VOIDED';
      notes = 'Self-elimination ignored (same squad)';
    }

    // Confidence routing (< 0.85 requires review if not manual)
    if (confidence < 0.85 && source === 'VISION_AI' && status === 'ACTIVE') {
      status = 'PENDING_REVIEW';
    }

    const eventId = `kill-${crypto.randomUUID()}`;
    const timestamp = new Date().toISOString();

    const stmt = this.db.prepare(`
      INSERT INTO kill_events (
        event_id, match_id, timestamp, match_time_sec,
        killer_player_id, killer_team_id,
        victim_player_id, victim_team_id,
        weapon, confidence, source, crop_path,
        status, notes
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      eventId,
      matchId,
      timestamp,
      matchTimeSec,
      killerPlayerId,
      killerTeamId,
      victimPlayerId,
      victimTeamId,
      weapon,
      confidence,
      source,
      cropPath,
      status,
      notes
    );

    // If ACTIVE, update victim team alive count and killer damage
    if (status === 'ACTIVE' && victimTeamId) {
      this.db.prepare(`
        UPDATE teams 
        SET alive_players = MAX(0, alive_players - 1)
        WHERE id = ? AND match_id = ?
      `).run(victimTeamId, matchId);

      if (killerTeamId) {
        this.db.prepare(`
          UPDATE teams
          SET damage_dealt = damage_dealt + 150
          WHERE id = ? AND match_id = ?
        `).run(killerTeamId, matchId);
      }
    }

    return {
      eventId,
      matchId,
      timestamp,
      killerTeamId,
      killerPlayerId,
      victimTeamId,
      victimPlayerId,
      weapon,
      confidence,
      status,
      source
    };
  }

  voidKillEvent(eventId) {
    const event = this.db.prepare('SELECT * FROM kill_events WHERE event_id = ?').get(eventId);
    if (!event) return null;

    this.db.prepare(`
      UPDATE kill_events SET status = 'VOIDED', notes = 'Voided by referee' WHERE event_id = ?
    `).run(eventId);

    // If it was ACTIVE, restore victim squad alive count
    if (event.status === 'ACTIVE' && event.victim_team_id) {
      this.db.prepare(`
        UPDATE teams
        SET alive_players = MIN(4, alive_players + 1)
        WHERE id = ? AND match_id = ?
      `).run(event.victim_team_id, event.match_id);
    }

    return { ...event, eventId: event.event_id, status: 'VOIDED' };
  }

  undoLastKill(matchId) {
    const lastActive = this.db.prepare(`
      SELECT * FROM kill_events 
      WHERE match_id = ? AND status = 'ACTIVE' 
      ORDER BY timestamp DESC, created_at DESC 
      LIMIT 1
    `).get(matchId);

    if (!lastActive) return null;

    return this.voidKillEvent(lastActive.event_id);
  }

  reassignKill(eventId, newKillerTeamId, newKillerPlayerId = null) {
    const oldEvent = this.db.prepare('SELECT * FROM kill_events WHERE event_id = ?').get(eventId);
    if (!oldEvent) return null;

    // Void old event
    this.voidKillEvent(eventId);

    // Insert corrected event
    return this.addKillEvent({
      matchId: oldEvent.match_id,
      killerTeamId: newKillerTeamId,
      killerPlayerId: newKillerPlayerId,
      victimTeamId: oldEvent.victim_team_id,
      victimPlayerId: oldEvent.victim_player_id,
      weapon: oldEvent.weapon,
      confidence: 1.0,
      source: 'MANUAL_REFEREE',
      status: 'ACTIVE',
      notes: `Reassigned from ${oldEvent.killer_team_id} to ${newKillerTeamId}`
    });
  }

  confirmReview(eventId) {
    const event = this.db.prepare('SELECT * FROM kill_events WHERE event_id = ?').get(eventId);
    if (!event) return null;

    this.db.prepare(`
      UPDATE kill_events SET status = 'ACTIVE', notes = 'Confirmed by referee' WHERE event_id = ?
    `).run(eventId);

    if (event.victim_team_id) {
      this.db.prepare(`
        UPDATE teams 
        SET alive_players = MAX(0, alive_players - 1)
        WHERE id = ? AND match_id = ?
      `).run(event.victim_team_id, event.match_id);
    }

    return { ...event, status: 'ACTIVE' };
  }

  rejectReview(eventId) {
    return this.voidKillEvent(eventId);
  }

  // Dynamic Aggregation & Deterministic Tie-Breaking
  getLeaderboard(matchId) {
    const teams = this.db.prepare(`
      SELECT 
        t.id,
        t.name,
        t.tag,
        t.country,
        t.logo,
        t.flag,
        t.default_rank,
        t.alive_players as alive,
        t.damage_dealt as damage,
        COUNT(CASE WHEN k.status = 'ACTIVE' THEN 1 ELSE NULL END) as elims,
        MIN(CASE WHEN k.status = 'ACTIVE' THEN k.timestamp ELSE NULL END) as first_kill_time
      FROM teams t
      LEFT JOIN kill_events k ON t.id = k.killer_team_id AND k.match_id = t.match_id
      WHERE t.match_id = ?
      GROUP BY t.id
    `).all(matchId);

    // Fetch players for each team
    const playersStmt = this.db.prepare(`
      SELECT ign, role, is_alive FROM players WHERE team_id = ? AND match_id = ?
    `);

    for (const team of teams) {
      const players = playersStmt.all(team.id, matchId);
      team.players = players.map(p => p.ign);
      team.playerDetails = players;
    }

    // Deterministic Tie-Breaker (Tech Stack Section 3.D):
    // 1. total_kills (elims) DESC
    // 2. alive_players DESC (active teams edge out eliminated teams on equal kills)
    // 3. first_to_reach_timestamp ASC (the team that scored first holds higher rank)
    // 4. default_rank ASC
    teams.sort((a, b) => {
      if (b.elims !== a.elims) {
        return b.elims - a.elims;
      }
      if (b.alive !== a.alive) {
        return b.alive - a.alive;
      }
      if (a.first_kill_time && b.first_kill_time) {
        if (a.first_kill_time !== b.first_kill_time) {
          return a.first_kill_time.localeCompare(b.first_kill_time);
        }
      } else if (a.first_kill_time) {
        return -1;
      } else if (b.first_kill_time) {
        return 1;
      }
      return a.default_rank - b.default_rank;
    });

    return teams;
  }

  getKillFeed(matchId, limit = 20) {
    return this.db.prepare(`
      SELECT 
        k.event_id as id,
        k.timestamp,
        k.match_time_sec,
        k.killer_team_id,
        kt.name as teamName,
        kt.logo as teamLogo,
        k.victim_team_id,
        vt.name as victimTeamName,
        k.weapon,
        k.confidence,
        k.source,
        k.status
      FROM kill_events k
      LEFT JOIN teams kt ON k.killer_team_id = kt.id AND k.match_id = kt.match_id
      LEFT JOIN teams vt ON k.victim_team_id = vt.id AND k.match_id = vt.match_id
      WHERE k.match_id = ? AND k.status = 'ACTIVE'
      ORDER BY k.timestamp DESC, k.created_at DESC
      LIMIT ?
    `).all(matchId, limit);
  }

  getPendingReviews(matchId) {
    return this.db.prepare(`
      SELECT 
        k.event_id as id,
        k.timestamp,
        k.killer_team_id,
        kt.name as killerTeamName,
        kt.logo as killerTeamLogo,
        k.victim_team_id,
        vt.name as victimTeamName,
        k.weapon,
        k.confidence,
        k.crop_path,
        k.source,
        k.status
      FROM kill_events k
      LEFT JOIN teams kt ON k.killer_team_id = kt.id AND k.match_id = kt.match_id
      LEFT JOIN teams vt ON k.victim_team_id = vt.id AND k.match_id = vt.match_id
      WHERE k.match_id = ? AND k.status = 'PENDING_REVIEW'
      ORDER BY k.timestamp ASC
    `).all(matchId);
  }

  getAllEvents(matchId, limit = 50) {
    return this.db.prepare(`
      SELECT 
        k.event_id as id,
        k.timestamp,
        k.killer_team_id,
        kt.name as killerTeamName,
        k.victim_team_id,
        vt.name as victimTeamName,
        k.weapon,
        k.confidence,
        k.source,
        k.status,
        k.notes
      FROM kill_events k
      LEFT JOIN teams kt ON k.killer_team_id = kt.id AND k.match_id = kt.match_id
      LEFT JOIN teams vt ON k.victim_team_id = vt.id AND k.match_id = vt.match_id
      WHERE k.match_id = ?
      ORDER BY k.timestamp DESC, k.created_at DESC
      LIMIT ?
    `).all(matchId, limit);
  }

  resetMatch(matchId) {
    this.db.prepare(`DELETE FROM kill_events WHERE match_id = ?`).run(matchId);
    this.db.prepare(`UPDATE teams SET alive_players = 4, damage_dealt = 0 WHERE match_id = ?`).run(matchId);
    this.db.prepare(`UPDATE players SET is_alive = 1 WHERE match_id = ?`).run(matchId);
    return true;
  }
}
