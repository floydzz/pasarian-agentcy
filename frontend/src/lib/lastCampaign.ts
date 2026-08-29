/** Which campaign the rail's studio shortcuts should open.
 *
 * The two studios are top-level entries because a person should never have to
 * dig through a campaign to reach their work. But a studio is still a room
 * inside a campaign, so the shortcut has to pick one — and the only defensible
 * pick is the campaign they were last in. Kept in `localStorage` because this
 * is a convenience for one browser, not state the machine should own.
 */
const KEY = 'agentcy.last-campaign'

export function rememberCampaign(id: number): void {
  if (!Number.isFinite(id)) return
  try {
    localStorage.setItem(KEY, String(id))
  } catch {
    /* private mode, or storage disabled — the shortcut just falls back */
  }
}

export function lastCampaign(): number | null {
  try {
    const stored = Number(localStorage.getItem(KEY))
    return Number.isFinite(stored) && stored > 0 ? stored : null
  } catch {
    return null
  }
}
