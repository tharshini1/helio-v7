// In production the FastAPI server serves this frontend, so the API lives on
// the same origin (empty base). In local dev, the backend runs on port 8001.
// Set VITE_API_URL to point the frontend at a different backend if needed.
export const API_BASE: string =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8001" : "");
