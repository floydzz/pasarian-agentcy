import type { BusinessEvent, CalendarEntry, MarketingItem, MarketingTask, Occasion } from '@/api/calendar'
import { labelDate } from '@/lib/marketingCalendar'

/** Read-only calendar facts; selecting a date never starts a planning run. */
export function CalendarEntryDetails({ entry, states = {} }: { entry: CalendarEntry; states?: Record<string, string> }) {
  if (entry.kind === 'business') return <p className="calendar-detail-copy">{(entry.details as BusinessEvent).description || 'No additional business details saved.'}</p>
  if (entry.kind === 'task') {
    const task = entry.details as MarketingTask & { item_title?: string }
    return <dl className="calendar-detail-fields"><div><dt>Due</dt><dd>{labelDate(task.due_date)} · {task.status === 'done' ? 'Completed' : 'To do'}</dd></div>{task.item_title && <div><dt>Campaign idea</dt><dd>{task.item_title}</dd></div>}</dl>
  }
  if (entry.kind === 'plan') {
    const item = entry.details as MarketingItem
    return <div className="calendar-entry-details">
      {item.strategy && <div><h3 className="calendar-detail-label">Strategy</h3><p className="calendar-detail-copy">{item.strategy}</p></div>}
      {item.rationale && <div><h3 className="calendar-detail-label">Why this occasion</h3><p className="calendar-detail-copy">{item.rationale}</p></div>}
      <dl className="calendar-detail-fields">
        {item.audience && <div><dt>Audience</dt><dd>{item.audience}</dd></div>}
        {item.products.length > 0 && <div><dt>Products</dt><dd>{item.products.join(', ')}</dd></div>}
        {item.offer && <div><dt>Proposed offer</dt><dd>{item.offer}</dd></div>}
        <div><dt>Budget estimate</dt><dd>{item.budget === null ? 'Not provided' : `MYR ${item.budget.toLocaleString('en-MY')}`}</dd></div>
        <div><dt>Campaign dates</dt><dd>{labelDate(item.campaign_start)} – {labelDate(item.campaign_end)}</dd></div>
        <div><dt>Preparation starts</dt><dd>{labelDate(item.preparation_start)}</dd></div>
        <div><dt>Status</dt><dd>{item.status}{item.campaign_status ? ` · ${item.campaign_status.replaceAll('_', ' ')}` : ''}</dd></div>
      </dl>
      {item.source_changed && <p className="calendar-detail-copy text-halt">The source details changed. Review the saved plan before continuing production.</p>}
      {item.tasks.length > 0 && <div><h3 className="calendar-detail-label">Preparation tasks</h3><ul className="calendar-detail-tasks">{item.tasks.map(task => <li key={task.id}><span>{task.title}</span><span className="text-text-3">{labelDate(task.due_date)} · {task.status === 'done' ? 'Completed' : 'To do'}</span></li>)}</ul></div>}
    </div>
  }
  const occasion = entry.details as Occasion
  return <div className="calendar-entry-details"><p className="calendar-detail-copy">{occasion.publication_status === 'tentative' ? 'Published date, subject to change.' : occasion.publication_status === 'withdrawn' ? 'Withdrawn. Review your planned campaign.' : 'Published official occasion.'}</p><dl className="calendar-detail-fields"><div><dt>Applies in</dt><dd>{occasion.states.map(code => states[code] ?? code).join(', ')}</dd></div><div><dt>Verified</dt><dd>{occasion.verified_at}</dd></div></dl><a className="calendar-detail-source" href={occasion.source_url} target="_blank" rel="noreferrer">Official source ↗</a></div>
}
