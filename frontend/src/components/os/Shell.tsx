import { useScrollMemory } from '@/hooks/useScrollMemory'
import { Suspense, useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, LayoutGroup, MotionConfig, motion } from 'motion/react'
import { MarketingChatDock } from '@/components/os/MarketingChatDock'
import { Sidebar } from '@/components/os/Sidebar'
import { STRATEGIST_MORPH } from '@/lib/motion'
import { finishRoomTransition } from '@/lib/rooms'

/** The frame every screen sits in.
 *
 * The rail is outside the scroll container and the page is inside it, so
 * navigation never scrolls away — the machine's other rooms stay one click
 * from wherever you are, including from a console mid-run.
 */
export function Shell() {
  const { pathname, search } = useLocation()
  const [chatOpen, setChatOpen] = useState(false)
  const [tabletUp, setTabletUp] = useState(() => window.matchMedia('(min-width: 768px)').matches)
  const launcherVisible = tabletUp || pathname.startsWith('/campaigns/')
  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)')
    const update = () => setTabletUp(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  // Any page can ask for the strategist with `?chat=open`; the bubble then
  // preserves the current route as its campaign context rather than taking
  // over the page with a dedicated chat destination.
  useEffect(() => {
    if (new URLSearchParams(search).get('chat') === 'open') setChatOpen(true)
  }, [search])

  return (
    <MotionConfig reducedMotion="user"><div className="flex h-dvh flex-col overflow-hidden bg-void md:flex-row text-foreground">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar />
      <main id="main-content"
        className={`relative min-h-0 min-w-0 flex-1 overflow-hidden pb-[calc(4rem+env(safe-area-inset-bottom))] transition-[margin] md:pb-0 duration-[420ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
          // On desktop the strategist is a dock, not a sheet over the work.
          // The studio therefore has its own visible width while chat remains
          // available. On a phone it intentionally stays an overlay.
          chatOpen && pathname !== '/chat' ? 'lg:mr-[27rem]' : ''
        }`}
      >
        <Suspense fallback={<p role="status" className="p-8 text-sm text-text-3">Loading workspace…</p>}><Outlet /></Suspense>
      </main>
      {/* Crossfade the complete panel into its launcher in one scoped morph.
          Full-page Chat stays outside this group. */}
      {pathname !== '/chat' && <LayoutGroup id="strategist-dock"><AnimatePresence initial={false}>
        {chatOpen ? (
          <MarketingChatDock key="strategist-panel" morphToLauncher={launcherVisible} onClose={() => { finishRoomTransition(); setChatOpen(false) }} />
        ) : (
          <motion.button
            key="strategist-launcher"
            layoutId={launcherVisible ? 'strategist' : undefined}
            type="button"
            onClick={() => { finishRoomTransition(); setChatOpen(true) }}
            aria-label="Open marketing strategist"
            transition={STRATEGIST_MORPH}
            style={{ borderRadius: 999 }}
            className={`group fixed right-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-40 ${pathname.startsWith('/campaigns/') ? 'flex' : 'hidden md:flex'} h-12 items-center border border-edge-strong bg-primary px-3 md:right-5 md:bottom-5 md:px-4 text-primary-foreground shadow-sm transition-colors hover:border-foreground`}
          >
            <motion.span layout="position" transition={STRATEGIST_MORPH} className="flex items-center gap-2">
            <span className="relative flex h-5 w-5 items-center justify-center rounded-full border border-edge">
              <span className="h-1.5 w-1.5 rounded-full bg-halt" />
            </span>
            <span className="display hidden text-[0.75rem] whitespace-nowrap md:inline">Strategist</span>
            </motion.span>
          </motion.button>
        )}
      </AnimatePresence></LayoutGroup>}
    </div></MotionConfig>
  )
}

/** A scrolling page inside the shell, with the shared measure and rhythm. */
export function Page({ children }: { children: React.ReactNode }) {
  const scroll = useScrollMemory()
  return (
    <div ref={scroll} className="quiet-scroll h-full min-w-0 overflow-y-auto">
      <div className="page-content mx-auto w-full max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
        {children}
      </div>
    </div>
  )
}
