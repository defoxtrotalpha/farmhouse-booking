import { useEffect, useState } from "react";
import { getHealth } from "./api.js";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640, margin: "0 auto" }}>
      <h1>Farmhouse Booking</h1>
      <p style={{ color: "#666" }}>Private, invite-only event-venue booking. Times shown in Asia/Karachi.</p>
      <section style={{ marginTop: "2rem", padding: "1rem 1.25rem", border: "1px solid #e5e5e5", borderRadius: 12 }}>
        <h2 style={{ margin: 0, fontSize: "1rem" }}>System status</h2>
        {error && <p style={{ color: "#b00020" }}>Backend unreachable: {error}</p>}
        {!error && !health && <p>Checking…</p>}
        {health && (
          <ul style={{ listStyle: "none", padding: 0 }}>
            <li>API: <strong>{health.status}</strong></li>
            <li>Database: <strong>{health.database}</strong></li>
            <li>Timezone: <strong>{health.timezone}</strong></li>
          </ul>
        )}
      </section>
    </main>
  );
}
