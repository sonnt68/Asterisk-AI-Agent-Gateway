# Troubleshooting

- **`4401` at WSS:** exchange a fresh API key token and verify the key was not
  revoked or expired.
- **`registration-rejected`:** use protocol version `1` and the app's exact
  agent slug.
- **`call-not-active`:** WSS is connected but the ARI worker has not assigned a
  call yet; do not retry call-control blindly.
- **No call at extension 9898:** on the PBX, verify `ari show apps` lists
  `asterisk-ai-gateway`; the test dialplan route is already present.
