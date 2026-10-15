import { useEffect, useState, type FormEvent } from 'react'
import { request } from '@/api/client'
import { useAuth } from '@/lib/auth'

type Result = { id: number; channel: string; period_start: string; period_end: string; spend: number; revenue: number; impressions: number; engagements: number; leads: number; sales: number; currency: string; notes: string; version: number }
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kuala_Lumpur' })
function blank() { return { channel: 'instagram', period_start: today(), period_end: today(), spend: 0, revenue: 0, impressions: 0, engagements: 0, leads: 0, sales: 0, currency: 'MYR', notes: '', version: 0 } }
export function CampaignResults({ campaignId }: { campaignId: number }) {
  const actor = useAuth()
  const [rows, setRows] = useState<Result[]>([])
  const [form, setForm] = useState(blank)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  useEffect(() => { void request<Result[]>(`/campaigns/${campaignId}/results`).then(setRows).catch(failure => setError(failure.message)).finally(() => setLoading(false)) }, [campaignId])
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await request(`/campaigns/${campaignId}/results`, { method: 'POST', body: JSON.stringify(form) })
      setRows(await request<Result[]>(`/campaigns/${campaignId}/results`)); setForm(blank()); setMessage('Results saved. The strategist can use this reported evidence in future recommendations.')
    } catch (failure) { setError((failure as Error).message) } finally { setBusy(false) }
  }
  return <section id="results" className="mt-8 scroll-mt-6 rounded-xl border border-edge bg-rise p-4 sm:p-5"><h2 className="font-medium">Campaign results</h2><p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-2">Record actual performance for each channel and reporting period. These are manually reported results; the strategist uses them as historical evidence. Keep periods separate to avoid double counting.</p>
    {error && <p role="alert" className="mt-4 text-sm text-halt">{error}</p>}{message && <p role="status" className="mt-4 text-sm text-brand">{message}</p>}
    {loading ? <p className="mt-4 text-sm text-text-3">Loading results…</p> : <ul className="mt-4 divide-y divide-edge">{rows.map(row => <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="min-w-0 text-sm"><p className="break-words font-medium">{row.channel} · {row.period_start} – {row.period_end}</p><p className="mt-1 break-words text-text-2">Spend {row.currency} {row.spend.toFixed(2)} · Revenue {row.currency} {row.revenue.toFixed(2)} · ROAS {row.spend > 0 ? (row.revenue / row.spend).toFixed(2) + '×' : 'unavailable'}</p><p className="mt-1 text-xs text-text-3">{row.impressions} impressions · {row.engagements} engagements · {row.leads} leads · {row.sales} sales</p></div>{['owner', 'editor'].includes(actor.role) && <button className="workspace-secondary" onClick={() => { const { id: _id, ...values } = row; setForm(values); setError(''); setMessage('Editing this reporting period. Save when finished.') }}>Edit results</button>}</li>)}{!rows.length && <li className="py-4 text-sm text-text-3">No performance results recorded yet.</li>}</ul>}
    {['owner', 'editor'].includes(actor.role) && <form className="mt-5 grid gap-4 border-t border-edge pt-5" onSubmit={save}><h3 className="text-sm font-medium">{form.version ? 'Edit reporting period' : 'Add reporting period'}</h3><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><label className="grid gap-2 text-sm">Channel<input required maxLength={40} className="workspace-input" value={form.channel} onChange={event => setForm({ ...form, channel: event.target.value })} readOnly={form.version > 0} /></label><label className="grid gap-2 text-sm">Period start<input required type="date" className="workspace-input" value={form.period_start} onChange={event => setForm({ ...form, period_start: event.target.value })} readOnly={form.version > 0} /></label><label className="grid gap-2 text-sm">Period end<input required type="date" min={form.period_start} className="workspace-input" value={form.period_end} onChange={event => setForm({ ...form, period_end: event.target.value })} readOnly={form.version > 0} /></label><label className="grid gap-2 text-sm">Currency<select className="workspace-input" value={form.currency} onChange={event => setForm({ ...form, currency: event.target.value })}><option>MYR</option><option>USD</option></select></label>{(['spend', 'revenue', 'impressions', 'engagements', 'leads', 'sales'] as const).map(key => <label key={key} className="grid gap-2 text-sm">{key[0].toUpperCase() + key.slice(1)}<input className="workspace-input" type="number" min={0} max={key === 'spend' || key === 'revenue' ? 1000000000 : 2000000000} step={key === 'spend' || key === 'revenue' ? '0.01' : '1'} required value={form[key]} onChange={event => setForm({ ...form, [key]: Number(event.target.value) })} /></label>)}</div><label className="grid gap-2 text-sm">Notes<textarea className="workspace-input" maxLength={2000} value={form.notes} onChange={event => setForm({ ...form, notes: event.target.value })} /></label><div className="flex flex-wrap gap-2"><button disabled={busy} className="workspace-button">{busy ? 'Saving…' : 'Save results'}</button>{form.version > 0 && <button type="button" className="workspace-secondary" onClick={() => setForm(blank())}>Cancel edit</button>}</div></form>}
  </section>
}
