import { useEffect } from 'react'

/** Mutations and completed background jobs invalidate currently visible data. */
export function useWorkspaceRefresh(refresh: () => void | Promise<void>) {
  useEffect(() => {
    let timer: number | undefined
    const changed = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => { void refresh() }, 100)
    }
    window.addEventListener('workspace-data-changed', changed)
    return () => { window.clearTimeout(timer); window.removeEventListener('workspace-data-changed', changed) }
  }, [refresh])
}
