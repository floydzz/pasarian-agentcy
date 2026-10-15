import { Aperture } from 'lucide-react'

export function PageError() {
  return <main className="grid min-h-dvh place-items-center bg-void px-6 text-foreground">
    <section className="w-full max-w-md rounded-2xl border border-edge bg-rise p-8">
      <div className="flex items-center gap-3 text-xl font-semibold"><Aperture className="text-brand" />agentcy.</div>
      <h1 className="mt-8 text-2xl font-semibold">This page couldn’t load</h1>
      <p className="mt-3 text-sm leading-relaxed text-text-2">Refresh to load the latest workspace. If this continues, check your connection and try again. Your account and saved work are still available.</p>
      <button className="workspace-button mt-6 justify-center" onClick={() => window.location.reload()}>Refresh workspace</button>
    </section>
  </main>
}
