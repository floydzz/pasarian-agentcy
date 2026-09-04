import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { MarketingChatDock } from '@/components/os/MarketingChatDock'
import { Sidebar } from '@/components/os/Sidebar'
import { DEPTH } from '@/lib/motion'

/** The frame every screen sits in.
 *
 * The rail is outside the scroll container and the page is inside it, so
 * navigation never scrolls away — the machine's other rooms stay one click
 * from wherever you are, including from a console mid-run.
 */
export function Shell() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const [chatOpen, setChatOpen] = useState(pathname === '/chat')

  // Old `/chat` links still work, but arrive in the new side-by-side workspace
  // rather than a separate room.
  useEffect(() => {
    if (pathname !== '/chat') return
    setChatOpen(true)
    navigate('/', { replace: true })
  }, [navigate, pathname])

  // Any page can ask for the strategist with `?chat=open`; the bubble then
  // preserves the current route as its campaign context rather than taking
  // over the page with a dedicated chat destination.
  useEffect(() => {
    if (new URLSearchParams(search).get('chat') === 'open') setChatOpen(true)
  }, [search])

  return (
    <div className="dark flex h-dvh overflow-hidden bg-void text-foreground">
      <Sidebar />
      <main className="relative min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
      {/* The bubble and the dock are one object at two sizes, so they are
          rendered as one branch under a single `AnimatePresence` and share a
          `layoutId`. Rendered as two independent elements, motion has nothing
          to measure the morph against and the strategist would pop. */}
      <AnimatePresence initial={false}>
        {chatOpen ? (
          <MarketingChatDock key="strategist" onClose={() => setChatOpen(false)} />
        ) : (
          <motion.button
            key="strategist"
            layoutId="strategist"
            type="button"
            onClick={() => setChatOpen(true)}
            aria-label="Open marketing strategist"
            transition={DEPTH}
            style={{ borderRadius: 999 }}
            className="fixed right-5 bottom-5 z-40 flex h-12 items-center gap-2 border border-edge-strong bg-rise px-4 text-foreground shadow-[0_12px_40px_rgba(0,0,0,0.45)] transition-colors hover:border-foreground"
          >
            <span className="relative flex h-5 w-5 items-center justify-center rounded-full border border-edge">
              <span className="h-1.5 w-1.5 rounded-full bg-halt" />
            </span>
            <span className="display text-[0.75rem] whitespace-nowrap">Strategist</span>
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}

/** A scrolling page inside the shell, with the shared measure and rhythm. */
export function Page({ children }: { children: React.ReactNode }) {
  return (
    <div className="quiet-scroll h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-12 sm:px-10 sm:py-16">
        {children}
      </div>
    </div>
  )
}
