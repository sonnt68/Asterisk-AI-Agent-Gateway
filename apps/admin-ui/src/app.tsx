const setupSteps = [
  "Connect the configured Asterisk",
  "Create a partner application",
  "Issue an API key",
  "Route a call to the agent",
];

export function App() {
  return (
    <main className="min-h-screen bg-slate-950 p-6 text-slate-100 sm:p-10">
      <section className="mx-auto max-w-5xl">
        <p className="text-sm font-medium tracking-wide text-cyan-300">ASTERISK AI AGENT GATEWAY</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Partner control plane</h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-300">
          A secure boundary between your Asterisk and third-party AI agents.
        </p>
        <div className="mt-10 rounded-2xl border border-slate-700 bg-slate-900/70 p-6 shadow-2xl">
          <h2 className="text-xl font-semibold">First-call setup</h2>
          <ol className="mt-5 space-y-3 text-slate-300">
            {setupSteps.map((step, index) => (
              <li className="flex gap-3" key={step}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-cyan-400 text-sm font-bold text-slate-950">
                  {index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
          <p className="mt-6 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
            Authentication and gateway configuration are not enabled yet. They will be added with tenant-scoped
            controls and audited API-key issuance.
          </p>
        </div>
      </section>
    </main>
  );
}
