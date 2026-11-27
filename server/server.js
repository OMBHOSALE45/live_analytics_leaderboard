import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { ScoreboardStore } from './scoreboard_store.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = process.env.PORT || 3001;
const DIST_PATH = path.join(__dirname, '..', 'frontend', 'dist');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon'
};

// Initialize In-Memory Scoreboard Store (Zero DB dependency)
const store = new ScoreboardStore();

// Connected clients for live streaming
const wsClients = new Set();
const sseClients = new Set();
const streamBarriers = new Map(); // barrierKey -> Map<streamId, timestampMs>

let pendingLiveState = null;
let liveStateWriteTimer = null;
let liveStateWriting = false;

async function flushLiveStateFiles() {
  if (liveStateWriting || !pendingLiveState) return;
  liveStateWriting = true;
  const state = pendingLiveState;
  pendingLiveState = null;
  try {
    const stateJson = JSON.stringify(state, null, 2);
    const targets = [
      path.join(__dirname, '..', 'frontend', 'public', 'live_state.json'),
      path.join(__dirname, '..', 'frontend', 'dist', 'live_state.json'),
      path.join(__dirname, 'live_state.json')
    ];
    await Promise.all(
      targets.map(async (t) => {
        try {
          await fs.promises.mkdir(path.dirname(t), { recursive: true });
          await fs.promises.writeFile(t, stateJson, 'utf8');
        } catch {}
      })
    );
  } finally {
    liveStateWriting = false;
    if (pendingLiveState) {
      setImmediate(flushLiveStateFiles);
    }
  }
}

function writeLiveStateFiles(state, immediate = false) {
  pendingLiveState = state;
  if (immediate) {
    if (liveStateWriteTimer) {
      clearTimeout(liveStateWriteTimer);
      liveStateWriteTimer = null;
    }
    setImmediate(flushLiveStateFiles);
    return;
  }
  if (!liveStateWriteTimer) {
    liveStateWriteTimer = setTimeout(() => {
      liveStateWriteTimer = null;
      flushLiveStateFiles();
    }, 250);
  }
}

function broadcastState(state) {
  const payload = JSON.stringify({
    type: 'leaderboard:update',
    timestamp: new Date().toISOString(),
    data: state
  });

  // Broadcast WebSocket
  for (const client of Array.from(wsClients)) {
    if (!client.destroyed && client.writable) {
      sendWsFrame(client, payload);
    } else {
      wsClients.delete(client);
    }
  }

  // Broadcast SSE
  for (const res of Array.from(sseClients)) {
    try {
      res.write(`data: ${payload}\n\n`);
    } catch {
      sseClients.delete(res);
    }
  }
}

// RFC 6455 Minimal WebSocket Implementation
function sendWsFrame(socket, message) {
  try {
    if (!socket || socket.destroyed || !socket.writable) {
      wsClients.delete(socket);
      return;
    }
    const payload = Buffer.from(message, 'utf8');
    const length = payload.length;
    let header;

    if (length < 126) {
      header = Buffer.from([0x81, length]);
    } else if (length < 65536) {
      header = Buffer.alloc(4);
      header[0] = 0x81;
      header[1] = 126;
      header.writeUInt16BE(length, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x81;
      header[1] = 127;
      header.writeBigUInt64BE(BigInt(length), 2);
    }

    socket.write(Buffer.concat([header, payload]));
  } catch {
    wsClients.delete(socket);
  }
}

// RFC 6455 Client Frame Unmasker & Action Handler
function handleClientFrame(socket, buf) {
  if (buf.length < 2) return;
  const firstByte = buf[0];
  const secondByte = buf[1];
  const opcode = firstByte & 0x0f;

  // Opcode 0x8: Connection Close Frame
  if (opcode === 0x8) {
    socket.end();
    wsClients.delete(socket);
    return;
  }
  // Opcode 0x9: Ping Frame -> Respond with Pong (0x8A)
  if (opcode === 0x9) {
    socket.write(Buffer.from([0x8A, 0x00]));
    return;
  }
  // Opcode 0x1: Text Frame
  if (opcode === 0x1) {
    const isMasked = Boolean(secondByte & 0x80);
    let payloadLen = secondByte & 0x7f;
    let offset = 2;
    if (payloadLen === 126) {
      if (buf.length < 4) return;
      payloadLen = buf.readUInt16BE(2);
      offset = 4;
    } else if (payloadLen === 127) {
      if (buf.length < 10) return;
      payloadLen = Number(buf.readBigUInt64BE(2));
      offset = 10;
    }
    if (!isMasked || buf.length < offset + 4 + payloadLen) return;
    const mask = buf.subarray(offset, offset + 4);
    offset += 4;
    const maskedData = buf.subarray(offset, offset + payloadLen);
    const unmasked = Buffer.alloc(maskedData.length);
    for (let i = 0; i < maskedData.length; i++) {
      unmasked[i] = maskedData[i] ^ mask[i % 4];
    }
    try {
      const msg = JSON.parse(unmasked.toString('utf8'));
      if (msg.action === 'reset') {
        const newState = store.reset();
        broadcastState(newState);
      }
    } catch {}
  }
}

function handleWsUpgrade(req, socket, head) {
  const key = req.headers['sec-websocket-key'];
  if (!key) {
    socket.destroy();
    return;
  }

  const acceptKey = crypto
    .createHash('sha1')
    .update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
    .digest('base64');

  const responseHeaders = [
    'HTTP/1.1 101 Switching Protocols',
    'Upgrade: websocket',
    'Connection: Upgrade',
    `Sec-WebSocket-Accept: ${acceptKey}`,
    '',
    ''
  ].join('\r\n');

  socket.setNoDelay(true);
  socket.write(responseHeaders);
  wsClients.add(socket);

  // Send initial state immediately
  const initState = JSON.stringify({
    type: 'init',
    timestamp: new Date().toISOString(),
    data: store.getState()
  });
  sendWsFrame(socket, initState);

  socket.on('data', (buf) => {
    try {
      handleClientFrame(socket, buf);
    } catch {}
  });

  socket.on('close', () => wsClients.delete(socket));
  socket.on('error', () => wsClients.delete(socket));
}

// HTTP Server
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost:' + PORT}`);

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  // SSE Stream endpoint
  if (url.pathname === '/api/stream') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive'
    });
    res.write(`data: ${JSON.stringify({ type: 'init', data: store.getState() })}\n\n`);
    sseClients.add(res);
    req.on('close', () => sseClients.delete(res));
    return;
  }

  // API: Sync Scoreboard from Python Vision Detector
  if (url.pathname === '/api/scoreboard/sync' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        const newState = store.syncScoreboard(payload);
        broadcastState(newState);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          status: 'SYNCED',
          teamsCount: newState.leaderboard.length,
          spectatedTeamName: newState.spectatorTeam?.name || null,
          spectatedColor: newState.spectatorTeam?.colorName || null
        }));

        // Async debounced fallback write AFTER WebSocket broadcast & HTTP reply
        writeLiveStateFiles(newState, false);
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  // API: Multi-stream ready barrier so parallel vision engines start frame-0 together
  if (url.pathname === '/api/streams/barrier' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const payload = body ? JSON.parse(body) : {};
        const key = String(payload.key || 'default');
        if (payload.reset) {
          streamBarriers.delete(key);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          return res.end(JSON.stringify({ reset: true, ready: false, arrived: 0 }));
        }

        const expected = Math.max(1, Number(payload.expected) || 1);
        const streamId = String(payload.streamId || 'default');
        const now = Date.now();
        let entry = streamBarriers.get(key);
        if (!entry) {
          entry = new Map();
          streamBarriers.set(key, entry);
        }
        // Drop stale registrations older than 30s so restarted runs never use old check-ins
        for (const [id, ts] of entry.entries()) {
          if (now - ts > 30000) entry.delete(id);
        }
        entry.set(streamId, now);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          ready: entry.size >= expected,
          arrived: entry.size,
          expected
        }));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  // API: Lobby 12-team slot-color mapping
  if (url.pathname === '/api/roster/colors' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ teamNames: store.teamNameMap }));
  }

  if (url.pathname === '/api/roster/colors' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const payload = body ? JSON.parse(body) : {};
        const newState = store.setTeamNameMap(payload.teamNames || payload);
        broadcastState(newState);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'SAVED', count: Object.keys(store.teamNameMap).length }));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  // API: Get Current Leaderboard
  if (url.pathname === '/api/leaderboard' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ leaderboard: store.teams }));
  }

  // API: Get Match Info & Standings
  if (url.pathname === '/api/match' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify(store.getState()));
  }

  // API: Reset Match
  if (url.pathname === '/api/match/reset' && req.method === 'POST') {
    const newState = store.reset();
    streamBarriers.clear();
    broadcastState(newState);
    writeLiveStateFiles(newState);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ success: true, message: 'Match reset' }));
  }

  // Health endpoint
  if (url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ status: 'ONLINE', port: PORT }));
  }

  // Serve Frontend UI (SPA from frontend/dist)
  if (fs.existsSync(DIST_PATH)) {
    let filePath = path.join(DIST_PATH, url.pathname === '/' ? 'index.html' : url.pathname);
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST_PATH, 'index.html');
    }
    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    try {
      const content = fs.readFileSync(filePath);
      res.writeHead(200, { 'Content-Type': contentType });
      return res.end(content);
    } catch {
      try {
        const fallback = fs.readFileSync(path.join(DIST_PATH, 'index.html'));
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end(fallback);
      } catch {
        // Fallback to 404
      }
    }
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Endpoint not found' }));
});

// Handle WebSocket Upgrades
server.on('upgrade', (req, socket, head) => {
  handleWsUpgrade(req, socket, head);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`====================================================`);
  console.log(` Free Fire Live Leaderboard Server (In-Memory Engine)`);
  console.log(` Port:           ${PORT}`);
  console.log(` Web UI:         http://localhost:${PORT}`);
  console.log(` OBS Overlay:    http://localhost:${PORT}/#/overlay`);
  console.log(` Referee Console:http://localhost:${PORT}/#/referee`);
  console.log(` Scoreboard Sync:POST http://localhost:${PORT}/api/scoreboard/sync`);
  console.log(` WebSocket:      ws://localhost:${PORT}`);
  console.log(`====================================================`);
});
