import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { MessageSquare, CalendarDays, Layers, Building2, SlidersHorizontal, TrendingUp, History, Image, Film, Activity, Download, Aperture, ChevronDown, LayoutDashboard, Menu } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useAuth } from '@/lib/auth'
import { api } from '@/api/client'
import type { System } from '@/api/types'
import { cn } from '@/lib/utils'
import { finishRoomTransition } from '@/lib/rooms'

const primary = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
  { to: '/campaigns', label: 'Campaigns', icon: Layers },
]
const groups = [
  { label: 'Work tools', links: [{ to: '/trends', label: 'Trends', icon: TrendingUp }, { to: '/progress', label: 'Progress', icon: Activity }, { to: '/publish', label: 'Publish', icon: Download }, { to: '/history', label: 'Run history', icon: History }] },
  { label: 'Studios', links: [{ to: '/studio/image', label: 'Image studio', icon: Image }, { to: '/studio/video', label: 'Video studio', icon: Film }] },
  { label: 'Settings', links: [{ to: '/brand', label: 'Brand', icon: Building2 }, { to: '/agents', label: 'Agent settings', icon: SlidersHorizontal }, { to: '/account', label: 'Account & team', icon: Building2 }] },
  { label: 'Demos', links: [{ to: '/demo-video', label: 'Product demo', icon: Film }, { to: '/cinematic-trailer/demo', label: 'Cinematic demo', icon: Film }] },
]

export function Sidebar() {
  const { pathname } = useLocation()
  const actor = useAuth()
  const savedDirectory = sessionStorage.getItem(`agentcy-directory:${actor.user.id}:${actor.workspace_id}`) ?? '/campaigns'
  const primaryLinks = primary.map(row => row.to === '/campaigns' ? { ...row, to: savedDirectory.startsWith('/campaigns') ? savedDirectory : '/campaigns' } : row)
  const [system, setSystem] = useState<System | null>(null)
  const [more, setMore] = useState(() => groups.some(g => g.links.some(l => pathname === l.to)))
  const [menu, setMenu] = useState(false)
  useEffect(() => { api.system().then(setSystem).catch(() => undefined) }, [])
  const openMenu = () => { finishRoomTransition(); setMenu(true) }
  const closeMenu = () => { finishRoomTransition(); setMenu(false) }
  const campaignActive = pathname === '/' || pathname.startsWith('/campaigns')
  const linkClass = (active: boolean) => cn('flex min-h-11 min-w-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors', active ? 'bg-accent font-medium text-foreground' : 'text-text-2 hover:bg-lift')
  const fullNavigation = <>
    <div className="space-y-1">{primaryLinks.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={closeMenu} className={({ isActive }) => linkClass(to.startsWith('/campaigns') ? campaignActive : isActive)}><Icon size={18} className="shrink-0" /><span>{label}</span></NavLink>)}</div>
    {groups.map(group => <section key={group.label} className="mt-5"><h3 className="mb-2 px-3 text-xs text-text-3">{group.label}</h3><div className="space-y-1">{group.links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={closeMenu} className={({ isActive }) => linkClass(isActive)}><Icon size={17} className="shrink-0" /><span>{label}</span></NavLink>)}</div></section>)}
  </>
  return <>
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-edge bg-rise px-4 md:hidden"><NavLink to="/dashboard" onClick={finishRoomTransition} className="flex items-center gap-2 font-semibold" aria-label="Agentcy home"><Aperture size={23} className="text-brand" />agentcy.</NavLink><button type="button" onClick={openMenu} aria-label="Open navigation menu" className="workspace-secondary min-h-9 px-3 py-1.5"><Menu size={17} />Menu</button></header>
    <nav aria-label="Main navigation" className="z-30 hidden h-full w-20 shrink-0 flex-col border-r border-edge bg-rise md:flex lg:w-[13.5rem]">
      <NavLink to="/dashboard" onClick={finishRoomTransition} className="flex h-20 shrink-0 items-center justify-center gap-3 px-4 text-foreground lg:justify-start lg:px-5" aria-label="Agentcy home"><Aperture size={26} className="shrink-0 text-brand" /><span className="hidden text-xl font-semibold tracking-tight lg:block">agentcy.</span></NavLink>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 lg:px-3"><p className="mb-3 hidden px-3 text-xs text-text-3 lg:block">Marketing workspace</p>
        {primaryLinks.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={finishRoomTransition} title={label} className={({ isActive }) => cn('mb-1 flex min-h-12 flex-col items-center justify-center gap-1 rounded-lg px-2 py-2 text-[.625rem] lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:text-sm', (to.startsWith('/campaigns') ? campaignActive : isActive) ? 'bg-accent font-medium text-foreground' : 'text-text-2 hover:bg-lift')}><Icon size={19} className="shrink-0" /><span>{label}</span></NavLink>)}
        <button type="button" onClick={openMenu} className="mt-5 flex min-h-11 w-full flex-col items-center justify-center gap-1 text-[.625rem] text-text-2 lg:hidden"><Menu size={17} />All pages</button>
        <button type="button" aria-expanded={more} onClick={() => setMore(!more)} className="mt-5 hidden min-h-11 w-full items-center justify-between px-3 text-xs text-text-2 lg:flex">Tools & settings<ChevronDown size={14} className={more ? 'rotate-180' : ''} /></button>
        {more && <div className="hidden pb-3 lg:block">{groups.map(group => <section key={group.label} className="mt-3"><h3 className="mb-1 px-3 text-[.6875rem] text-text-3">{group.label}</h3>{group.links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={finishRoomTransition} className={({ isActive }) => linkClass(isActive)}><Icon size={17} className="shrink-0" /><span>{label}</span></NavLink>)}</section>)}</div>}
      </div>
      <NavLink to="/account" className="mx-3 my-4 min-w-0 rounded-lg bg-void p-2 text-center text-[.625rem] text-text-2 lg:text-left lg:text-xs"><span className="block truncate">{actor.workspaces.find(row => row.id === actor.workspace_id)?.name}</span><span className="mt-1 block text-text-3">{actor.role} · {system?.scripted_demo || system?.llm_provider === 'demo' ? 'Demo mode' : 'Account'}</span></NavLink>
    </nav>
    <nav aria-label="Mobile shortcuts" className="mobile-shortcuts fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-edge bg-rise md:hidden">{primaryLinks.slice(0, 4).map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={finishRoomTransition} className={({ isActive }) => cn('flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-[.6875rem]', (to.startsWith('/campaigns') ? campaignActive : isActive) ? 'font-medium text-brand' : 'text-text-2')}><Icon size={18} /><span>{label}</span></NavLink>)}</nav>
    <Dialog open={menu} onOpenChange={setMenu}><DialogContent className="left-0 top-0 h-dvh w-[min(90vw,22rem)] max-w-none translate-x-0 translate-y-0 content-start overflow-y-auto rounded-none p-5"><DialogTitle>Navigate your workspace</DialogTitle><DialogDescription>Choose a page or tool.</DialogDescription><nav aria-label="Navigation menu" className="mt-2">{fullNavigation}</nav></DialogContent></Dialog>
  </>
}

export function PageHead({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <header className="flex min-w-0 flex-wrap items-start justify-between gap-4"><div className="min-w-0 flex-[1_1_18rem]"><h1 className="display-tight break-words text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-2">{children}</p></div>{action}</header>
}
