import axios from "axios";

/**
 * Control-plane client. The gateway authenticates browsers with an httpOnly
 * `gateway_session` cookie, so every request must carry credentials and no
 * token is ever held in JavaScript.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_GATEWAY_API_URL ?? "/api/v1",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});
