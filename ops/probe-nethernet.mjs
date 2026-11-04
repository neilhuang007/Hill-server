import { createRequire } from 'node:module';
import path from 'node:path';
import { writeFileSync } from 'node:fs';
import { isIP } from 'node:net';

const target = new URL(process.argv[2]);
const host = target.hostname;
if (target.protocol !== 'http:' || !isIP(host)
    || !(/^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)))
  throw new Error('This probe is only for a local IPv4 signaling address.');
const dependencies = process.env.HILL175_BEDROCK_SMOKE_DEPS
  ?? path.join(process.env.LOCALAPPDATA, 'Hill175/bedrock-deps');
const require = createRequire(path.join(dependencies, 'package.json'));
const { RTCPeerConnection } = require('werift');
const response = await fetch(new URL('/v1/join', target), {signal: AbortSignal.timeout(15000)});
if (!response.ok) throw new Error(`NetherNet discovery failed: ${response.status}`);
const info = await response.json();
if (!info.protocol || !info.version) throw new Error('Missing NetherNet version advertisement.');
const peer = new RTCPeerConnection({iceServers: []});
try {
  peer.createDataChannel('ReliableDataChannel', {negotiated: true, id: 0, ordered: true});
  peer.createDataChannel('UnreliableDataChannel', {negotiated: true, id: 1, ordered: false, maxRetransmits: 0});
  await peer.setLocalDescription(await peer.createOffer());
  const rejected = await fetch(new URL('/v1/join/' + Date.now(), target), {
    method: 'POST', headers: {'Content-Type': 'application/sdp'},
    body: peer.localDescription.sdp, signal: AbortSignal.timeout(15000),
  });
  if (![400,401,403].includes(rejected.status))
    throw new Error(`Unsigned WebRTC offer was not rejected: ${rejected.status}`);
  const result = {success: true, target: target.origin, advertisement: info,
    unsignedOfferStatus: rejected.status, scope: 'HTTP discovery and rejection of an unsigned WebRTC offer. No signed 26.60 gameplay claim.'};
  console.log(JSON.stringify(result, null, 2));
  if (process.argv[3]) writeFileSync(process.argv[3], JSON.stringify(result, null, 2));
} finally {
  await peer.close();
}
