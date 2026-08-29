import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { MarketingChatDock } from '@/components/os/MarketingChatDock'
import { Sidebar } from '@/components/os/Sidebar'

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
      <MarketingChatDock open={chatOpen} onClose={() => setChatOpen(false)} />
      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          aria-label="Open marketing strategist"
          className="fixed right-5 bottom-5 z-40 flex h-12 items-center gap-2 rounded-full border border-edge-strong bg-rise px-4 text-foreground shadow-[0_12px_40px_rgba(0,0,0,0.45)] transition-colors hover:border-foreground"
        >
          <span className="relative flex h-5 w-5 items-center justify-center rounded-full border border-edge">
            <span className="h-1.5 w-1.5 rounded-full bg-halt" />
          </span>
          <span className="display text-[0.75rem]">Strategist</span>
        </button>
      )}
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
