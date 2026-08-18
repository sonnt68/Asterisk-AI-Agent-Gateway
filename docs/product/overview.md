# Product Overview

The Asterisk AI Agent Gateway is a centrally operated SaaS integration layer
between one configured Asterisk and third-party AI agent applications.

The gateway owns Asterisk connectivity and real-time call lifecycle handling.
Partners authenticate with issued API keys, receive a short-lived realtime
session, and exchange audio and call-control messages through the gateway.

## Partner Boundary

Partners do not receive ARI, SIP, AudioSocket, RTP, server-shell, or Docker
credentials. They integrate through documented REST, WebSocket, and SDK
surfaces only.

## MVP Boundary

- One configured Asterisk per gateway deployment.
- Inbound and outbound call workflows.
- DTMF, hold/resume, mute/unmute, hangup, blind/attended transfer, transfer
  cancellation, queue/ring-group/voicemail routing, and outbound originate
  controls.
- Recording and transcription are disabled by default.
