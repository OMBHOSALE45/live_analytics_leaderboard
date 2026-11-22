import crypto from 'node:crypto';

const WS_MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

export class BroadcastHub {
  constructor(ledger) {
    this.ledger = ledger;
    this.wsClients = new Set();
    this.sseClients = new Set();
  }

  // Handle HTTP Upgrade to WebSocket
  handleUpgrade(req, socket, head) {
    const key = req.headers['sec-websocket-key'];
    if (!key) {
      socket.destroy();
      return;
    }

    const acceptKey = crypto
      .createHash('sha1')
      .update(key + WS_MAGIC_STRING)
      .digest('base64');

    const headers = [
      'HTTP/1.1 101 Switching Protocols',
      'Upgrade: websocket',
      'Connection: Upgrade',
      `Sec-WebSocket-Accept: ${acceptKey}`,
      '\r\n'
    ];

    socket.write(headers.join('\r\n'));

    const client = {
      socket,
      id: crypto.randomUUID()
    };

    this.wsClients.add(client);

    // Send initial state upon connection
    this.sendToClient(client, {
      type: 'init',
      data: this.getFullState()
    });

    let buffer = Buffer.alloc(0);

    socket.on('data', (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      buffer = this.parseFrames(buffer, (message) => {
        this.handleMessage(client, message);
      });
    });

    socket.on('close', () => {
      this.wsClients.delete(client);
    });

    socket.on('error', () => {
      this.wsClients.delete(client);
      socket.destroy();
    });
  }

  // Parse RFC 6455 WebSocket Frames from client
  parseFrames(buffer, onMessage) {
    while (buffer.length >= 2) {
      const firstByte = buffer[0];
      const secondByte = buffer[1];
      const opcode = firstByte & 0x0f;
      const isMasked = (secondByte & 0x80) !== 0;
      let payloadLength = secondByte & 0x7f;
      let offset = 2;

      // Close frame
      if (opcode === 0x08) {
        return Buffer.alloc(0);
      }

      if (payloadLength === 126) {
        if (buffer.length < 4) return buffer;
        payloadLength = buffer.readUInt16BE(2);
        offset = 4;
      } else if (payloadLength === 127) {
        if (buffer.length < 10) return buffer;
        payloadLength = Number(buffer.readBigUInt64BE(2));
        offset = 10;
      }

      const maskLength = isMasked ? 4 : 0;
      if (buffer.length < offset + maskLength + payloadLength) {
        return buffer; // wait for more data
      }

      let payload = buffer.subarray(offset + maskLength, offset + maskLength + payloadLength);

      if (isMasked) {
        const maskKey = buffer.subarray(offset, offset + 4);
        const unmasked = Buffer.alloc(payloadLength);
        for (let i = 0; i < payloadLength; i++) {
          unmasked[i] = payload[i] ^ maskKey[i % 4];
        }
        payload = unmasked;
      }

      if (opcode === 0x01) { // Text frame
        try {
          const text = payload.toString('utf8');
          const data = JSON.parse(text);
          onMessage(data);
        } catch (e) {
          console.error('WS JSON parse error:', e.message);
        }
      }

      buffer = buffer.subarray(offset + maskLength + payloadLength);
    }
    return buffer;
  }

  // Encode message into unmasked RFC 6455 server-to-client frame
  encodeFrame(data) {
    const jsonStr = JSON.stringify(data);
    const payload = Buffer.from(jsonStr, 'utf8');
    const length = payload.length;

    let header;
    if (length < 126) {
      header = Buffer.alloc(2);
      header[0] = 0x81; // FIN + text
      header[1] = length;
    } else if (length <= 0xffff) {
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

    return Buffer.concat([header, payload]);
  }

  sendToClient(client, message) {
    try {
      const frame = this.encodeFrame(message);
      client.socket.write(frame);
    } catch (e) {
      this.wsClients.delete(client);
    }
  }

  // Handle SSE Clients
  handleSSE(req, res) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });

    const sseClient = { res, id: crypto.randomUUID() };
    this.sseClients.add(sseClient);

    // Send initial state
    res.write(`data: ${JSON.stringify({ type: 'init', data: this.getFullState() })}\n\n`);

    req.on('close', () => {
      this.sseClients.delete(sseClient);
    });
  }

  // Broadcast to all connected WebSocket and SSE clients
  broadcast(type, payload) {
    const message = { type, data: payload, timestamp: new Date().toISOString() };
    const frame = this.encodeFrame(message);

    for (const client of this.wsClients) {
      try {
        client.socket.write(frame);
      } catch (e) {
        this.wsClients.delete(client);
      }
    }

    const sseData = `data: ${JSON.stringify(message)}\n\n`;
    for (const sse of this.sseClients) {
      try {
        sse.res.write(sseData);
      } catch (e) {
        this.sseClients.delete(sse);
      }
    }
  }

  getFullState() {
    const match = this.ledger.getActiveMatch();
    if (!match) return { match: null, leaderboard: [], killFeed: [], pendingReviews: [] };

    const leaderboard = this.ledger.getLeaderboard(match.id);
    const killFeed = this.ledger.getKillFeed(match.id, 25);
    const pendingReviews = this.ledger.getPendingReviews(match.id);
    const allEvents = this.ledger.getAllEvents(match.id, 50);

    return {
      match,
      leaderboard,
      killFeed,
      pendingReviews,
      allEvents
    };
  }

  broadcastStateUpdate() {
    const state = this.getFullState();
    this.broadcast('leaderboard:update', state);
  }

  handleMessage(client, msg) {
    const { action, payload } = msg;
    const match = this.ledger.getActiveMatch();
    const matchId = match?.id || 'ffws-2025-gf-match-4';

    switch (action) {
      case 'kill:add': {
        this.ledger.addKillEvent({
          matchId,
          killerTeamId: payload.killerTeamId,
          killerPlayerId: payload.killerPlayerId,
          victimTeamId: payload.victimTeamId,
          victimPlayerId: payload.victimPlayerId,
          weapon: payload.weapon || 'SCAR',
          confidence: payload.confidence ?? 1.0,
          source: payload.source || 'MANUAL_REFEREE',
          status: payload.status || 'ACTIVE'
        });
        this.broadcastStateUpdate();
        break;
      }

      case 'kill:void': {
        if (payload?.eventId) {
          this.ledger.voidKillEvent(payload.eventId);
          this.broadcastStateUpdate();
        }
        break;
      }

      case 'kill:undo': {
        this.ledger.undoLastKill(matchId);
        this.broadcastStateUpdate();
        break;
      }

      case 'kill:reassign': {
        if (payload?.eventId && payload?.newKillerTeamId) {
          this.ledger.reassignKill(payload.eventId, payload.newKillerTeamId, payload.newKillerPlayerId);
          this.broadcastStateUpdate();
        }
        break;
      }

      case 'review:confirm': {
        if (payload?.eventId) {
          this.ledger.confirmReview(payload.eventId);
          this.broadcastStateUpdate();
        }
        break;
      }

      case 'review:reject': {
        if (payload?.eventId) {
          this.ledger.rejectReview(payload.eventId);
          this.broadcastStateUpdate();
        }
        break;
      }

      case 'match:reset': {
        this.ledger.resetMatch(matchId);
        this.broadcastStateUpdate();
        break;
      }

      default:
        console.log('Unknown action received:', action);
    }
  }
}

