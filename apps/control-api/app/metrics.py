"""Low-cardinality runtime metrics; identifiers stay in structured logs."""

from prometheus_client import Counter, Gauge, Histogram

active_calls = Gauge("gateway_active_calls", "Active gateway-owned calls")
ari_connected = Gauge("gateway_ari_connected", "Whether the ARI event listener is connected")
active_connections = Gauge("gateway_active_partner_connections", "Active partner WSS sessions")
audiosocket_connections = Gauge(
    "gateway_active_audiosocket_connections", "Active Asterisk AudioSocket sessions"
)
audio_bytes = Counter(
    "gateway_audio_bytes_total", "Audio payload bytes routed", labelnames=("direction",)
)
ari_events = Counter("gateway_ari_events_total", "ARI events handled", labelnames=("type",))
command_outcomes = Counter(
    "gateway_call_commands_total", "Partner call commands", labelnames=("outcome",)
)
partner_audio_queue_depth = Gauge(
    "gateway_partner_audio_queue_depth", "Queued partner-bound audio frames"
)
partner_audio_drops = Counter(
    "gateway_partner_audio_drops_total", "Dropped partner-bound audio frames"
)
rate_limit_rejections = Counter(
    "gateway_rate_limit_rejections_total",
    "Requests rejected by a gateway rate limit",
    labelnames=("surface",),
)
call_setup_seconds = Histogram(
    "gateway_call_setup_seconds",
    "Time from Stasis handling to partner call.started",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
call_outcomes = Counter(
    "gateway_calls_total", "Gateway call lifecycle outcomes", labelnames=("outcome",)
)
partner_disconnects = Counter(
    "gateway_partner_disconnects_total", "Partner realtime disconnections"
)
