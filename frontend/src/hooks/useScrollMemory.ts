import { useLayoutEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '@/lib/auth'

/** Restore nested page scrolling after async content returns, without fighting input. */
export function useScrollMemory() {
  const ref = useRef<HTMLDivElement>(null)
  const actor = useAuth()
  const { pathname, search } = useLocation()
  const storageKey = `agentcy-scroll:${actor.user.id}:${actor.workspace_id}:${pathname}${search}`
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const target = Number(sessionStorage.getItem(storageKey)) || 0
    if (!target) element.scrollTop = 0
    let restoring = target > 0
    let timer: number | undefined
    const save = () => { if (!restoring) { if (element.scrollTop > 0) sessionStorage.setItem(storageKey, String(element.scrollTop)); else sessionStorage.removeItem(storageKey) } }
    const stop = () => { restoring = false; observer.disconnect(); mutations.disconnect() }
    const restore = () => {
      if (!restoring) return
      element.scrollTop = target
      if (Math.abs(element.scrollTop - target) < 2) stop()
    }
    const observer = new ResizeObserver(restore)
    const mutations = new MutationObserver(restore)
    mutations.observe(element, { childList: true, subtree: true })
    if (element.firstElementChild) observer.observe(element.firstElementChild)
    const scrolled = () => { window.clearTimeout(timer); timer = window.setTimeout(save, 100) }
    element.addEventListener('scroll', scrolled, { passive: true })
    for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) element.addEventListener(event, stop, { passive: true })
    restore()
    const deadline = window.setTimeout(stop, 5000)
    return () => {
      save(); observer.disconnect(); mutations.disconnect(); window.clearTimeout(timer); window.clearTimeout(deadline)
      element.removeEventListener('scroll', scrolled)
      for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) element.removeEventListener(event, stop)
    }
  }, [storageKey])
  return ref
}
