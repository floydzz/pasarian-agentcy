import { Outlet } from 'react-router-dom'
import { Sidebar } from '@/components/os/Sidebar'

/** The frame every screen sits in.
 *
 * The rail is outside the scroll container and the page is inside it, so
 * navigation never scrolls away — the machine's other rooms stay one click
 * from wherever you are, including from a console mid-run.
 */
export function Shell() {
  return (
    <div className="dark flex h-dvh overflow-hidden bg-void text-foreground">
      <Sidebar />
      <main className="relative min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
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
