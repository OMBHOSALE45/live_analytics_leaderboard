export function createRouter(ledger, hub) {
  return async function handleApiRequest(req, res) {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost:3001'}`);
    const pathname = url.pathname;
    const method = req.method.toUpperCase();

    // CORS Headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    const sendJson = (statusCode, data) => {
      res.writeHead(statusCode, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    };

    const parseBody = () => new Promise((resolve) => {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          resolve(body ? JSON.parse(body) : {});
        } catch (e) {
          resolve({});
        }
      });
    });

    const match = ledger.getActiveMatch();
    const matchId = match?.id || 'ffws-2025-gf-match-4';

    // GET /api/match
    if (method === 'GET' && pathname === '/api/match') {
      return sendJson(200, {
        match,
        leaderboard: ledger.getLeaderboard(matchId),
        stats: ledger.getMatchStats(matchId)
      });
    }

    // GET /api/leaderboard
    if (method === 'GET' && pathname.startsWith('/api/leaderboard')) {
      const lb = ledger.getLeaderboard(matchId);
      return sendJson(200, { leaderboard: lb });
    }

    // GET /api/kills
    if (method === 'GET' && pathname.startsWith('/api/kills')) {
      const kills = ledger.getKillFeed(matchId, 50);
      return sendJson(200, { kills });
    }

    // GET /api/events (all events for referee)
    if (method === 'GET' && pathname.startsWith('/api/events')) {
      const events = ledger.getAllEvents(matchId, 100);
      return sendJson(200, { events });
    }

    // GET /api/reviews
    if (method === 'GET' && pathname.startsWith('/api/reviews')) {
      const reviews = ledger.getPendingReviews(matchId);
      return sendJson(200, { reviews });
    }

    // POST /api/kill - Add kill event
    if (method === 'POST' && pathname === '/api/kill') {
      const body = await parseBody();
      const event = ledger.addKillEvent({
        matchId,
        killerTeamId: body.killerTeamId,
        killerPlayerId: body.killerPlayerId,
        victimTeamId: body.victimTeamId,
        victimPlayerId: body.victimPlayerId,
        weapon: body.weapon || 'SCAR',
        confidence: body.confidence !== undefined ? body.confidence : 1.0,
        source: body.source || 'MANUAL_REFEREE',
        status: body.status || 'ACTIVE'
      });

      hub.broadcastStateUpdate();
      return sendJson(201, { success: true, event });
    }

    // POST /api/kill/undo
    if (method === 'POST' && pathname === '/api/kill/undo') {
      const undone = ledger.undoLastKill(matchId);
      hub.broadcastStateUpdate();
      return sendJson(200, { success: !!undone, event: undone });
    }

    // DELETE /api/kill/:id
    if (method === 'DELETE' && pathname.startsWith('/api/kill/')) {
      const eventId = pathname.replace('/api/kill/', '');
      const voided = ledger.voidKillEvent(eventId);
      hub.broadcastStateUpdate();
      return sendJson(200, { success: !!voided, event: voided });
    }

    // POST /api/review/:id/confirm
    if (method === 'POST' && pathname.includes('/confirm')) {
      const parts = pathname.split('/');
      const eventId = parts[3];
      const confirmed = ledger.confirmReview(eventId);
      hub.broadcastStateUpdate();
      return sendJson(200, { success: !!confirmed, event: confirmed });
    }

    // POST /api/review/:id/reject
    if (method === 'POST' && pathname.includes('/reject')) {
      const parts = pathname.split('/');
      const eventId = parts[3];
      const rejected = ledger.rejectReview(eventId);
      hub.broadcastStateUpdate();
      return sendJson(200, { success: !!rejected, event: rejected });
    }

    // POST /api/match/reset
    if (method === 'POST' && pathname === '/api/match/reset') {
      ledger.resetMatch(matchId);
      hub.broadcastStateUpdate();
      return sendJson(200, { success: true, message: 'Match reset' });
    }

    // 404 for unknown endpoints
    return sendJson(404, { error: 'Not found', path: pathname });
  };
}

