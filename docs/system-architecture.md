# System architecture

The gateway solely owns ARI credentials, Asterisk channel/bridge IDs,
AudioSocket and cleanup. A partner owns an API key, agent slug and outbound WSS.

```text
Asterisk ARI -> lifecycle -> bridge + AudioSocket(slin, rate configurable)
                                  |
                         gateway call UUID
                                  |
Partner SDK <- JSON + UUID/PCM <- realtime WSS
     |
short token <- API key hash <- PostgreSQL
connection lease <- Redis
```

One globally unique agent slug maps the single MVP Asterisk route to one healthy
connection. Partner disconnect hangs up owned active calls.
