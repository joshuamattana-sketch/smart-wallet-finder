"use client";

// Root error boundary — catches failures in the root layout itself, so even a
// top-level crash renders a styled page instead of the browser default.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "14px",
          background: "#0c0c0e",
          color: "#e0e0e4",
          fontFamily: "system-ui, sans-serif",
          textAlign: "center",
          padding: "1rem",
        }}
      >
        <h1 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>Something went wrong</h1>
        <p style={{ fontSize: "13px", color: "#a1a1a6", maxWidth: "24rem", margin: 0 }}>
          The app hit an unexpected error. Please reload.
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            minHeight: "40px",
            padding: "0 20px",
            borderRadius: "6px",
            border: "none",
            background: "#22d3ee",
            color: "#09090b",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
