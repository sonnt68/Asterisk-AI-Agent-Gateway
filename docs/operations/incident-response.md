# Incident response

For a suspected key leak, revoke the affected key in the dashboard, issue a
replacement, and audit token exchanges. For ARI loss, stop assigning new calls,
restore private connectivity, then verify `ari show apps` and gateway readiness.
Do not recover by exposing ARI publicly or sharing PBX credentials with partners.
