import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Aperture, LockKeyhole } from 'lucide-react'
import { ApiError, request, setSessionToken } from '@/api/client'

import { Auth, type Identity } from '@/lib/auth'

export function AuthGate({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [setup, setSetup] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let current = true
    const expired = () => { setSessionToken(''); setIdentity(null) }
    window.addEventListener('authentication-required', expired)
    request<{ setup_required: boolean }>('/auth/status').then(async status => {
      if (!current) return
      setSetup(status.setup_required)
      if (!status.setup_required) {
        try {
          const actor = await request<Identity>('/auth/me')
          if (current) { setSessionToken(actor.csrf_token); setIdentity(actor) }
        } catch (failure) { if (!(failure instanceof ApiError && failure.status === 401)) throw failure }
      }
    }).catch(failure => current && setError((failure as Error).message)).finally(() => current && setLoading(false))
    return () => { current = false; window.removeEventListener('authentication-required', expired) }
  }, [retry])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const values = Object.fromEntries(new FormData(event.currentTarget))
    try {
      const actor = await request<Identity>(setup ? '/auth/setup' : '/auth/login', { method: 'POST', body: JSON.stringify(values) })
      setSessionToken(actor.csrf_token); setIdentity(actor)
    } catch (failure) { setError((failure as Error).message) } finally { setBusy(false) }
  }
  if (identity) return <Auth.Provider value={identity}>{children}</Auth.Provider>
  return <main className="grid min-h-dvh place-items-center bg-void px-4 py-10 text-foreground">
    <section className="w-full max-w-md rounded-2xl border border-edge bg-rise p-6 sm:p-8">
      <div className="flex items-center gap-3 text-xl font-semibold"><Aperture className="text-brand" />agentcy.</div>
      <h1 className="mt-8 text-2xl font-semibold">{loading ? 'Opening your workspace…' : setup ? 'Set up your workspace' : 'Welcome back'}</h1>
      <p className="mt-3 text-sm leading-relaxed text-text-2">{setup ? 'Create the owner account for your existing marketing work. You need the local setup code to continue.' : 'Sign in to your marketing workspace. Your campaigns, conversations and brand knowledge stay together.'}</p>
      {error && <div role="alert" className="mt-5 rounded-lg border border-halt/50 p-3 text-sm text-halt">{error}<button type="button" onClick={() => { setError(''); setLoading(true); setRetry(value => value + 1) }} className="ml-2 underline">Retry connection</button></div>}
      {!loading && <form onSubmit={submit} className="mt-6 grid gap-4">
        {setup && <><label className="grid gap-2 text-sm">Your name<input name="name" required maxLength={120} autoComplete="name" className="workspace-input" /></label><label className="grid gap-2 text-sm">Workspace name<input name="workspace_name" required maxLength={200} className="workspace-input" /></label><label className="grid gap-2 text-sm">Setup code<input name="setup_token" required type="password" autoComplete="off" className="workspace-input" /><span className="text-xs leading-relaxed text-text-3">Your local installation keeps this code in its private bootstrap file. It is only needed for initial ownership.</span></label></>}
        <label className="grid gap-2 text-sm">Email<input name="email" type="email" required autoComplete="username" className="workspace-input" /></label>
        <label className="grid gap-2 text-sm">Password<input name="password" type="password" required minLength={12} maxLength={128} autoComplete={setup ? 'new-password' : 'current-password'} className="workspace-input" />{setup && <span className="text-xs text-text-3">Use at least 12 characters.</span>}</label>
        <button disabled={busy} className="workspace-button mt-2 justify-center">{busy ? 'Please wait…' : setup ? 'Create owner account' : 'Sign in'}</button>
      </form>}
      <p className="mt-6 flex items-center gap-2 text-xs text-text-3"><LockKeyhole size={14} />Private workspace · Access controlled by your owner</p>
    </section>
  </main>
}
