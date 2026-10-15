import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from 'react-router-dom'
import { AuthGate } from '@/components/AuthGate'
import { PageError } from '@/components/PageError'
import { Toaster } from '@/components/ui/sonner'
import { Shell } from '@/components/os/Shell'
import { lazy } from 'react'
const Account = lazy(() => import('@/pages/Account').then(module => ({ default: module.Account })))
const Dashboard = lazy(() => import('@/pages/Dashboard').then(module => ({ default: module.Dashboard })))
const Agents = lazy(() => import('@/pages/Agents').then(module => ({ default: module.Agents })))
const BrandProfile = lazy(() => import('@/pages/BrandProfile').then(module => ({ default: module.BrandProfile })))
const CampaignHub = lazy(() => import('@/pages/CampaignHub').then(module => ({ default: module.CampaignHub })))
const CinematicTrailer = lazy(() => import('@/pages/CinematicTrailer').then(module => ({ default: module.CinematicTrailer })))
const DemoVideo = lazy(() => import('@/pages/DemoVideo').then(module => ({ default: module.DemoVideo })))
const History = lazy(() => import('@/pages/History').then(module => ({ default: module.History })))
const Calendar = lazy(() => import('@/pages/Calendar').then(module => ({ default: module.Calendar })))
const Chat = lazy(() => import('@/pages/Chat').then(module => ({ default: module.Chat })))
const Home = lazy(() => import('@/pages/Home').then(module => ({ default: module.Home })))
const ImageStudio = lazy(() => import('@/pages/studio/ImageStudio').then(module => ({ default: module.ImageStudio })))
const StudioShortcut = lazy(() => import('@/pages/studio/StudioShortcut').then(module => ({ default: module.StudioShortcut })))
const Trends = lazy(() => import('@/pages/Trends').then(module => ({ default: module.Trends })))
const VideoStudio = lazy(() => import('@/pages/studio/VideoStudio').then(module => ({ default: module.VideoStudio })))
const Progress = lazy(() => import('@/pages/Progress').then(module => ({ default: module.Progress })))
const Publish = lazy(() => import('@/pages/Publish').then(module => ({ default: module.Publish })))

/** A data router rather than `BrowserRouter`.
 *
 * The room transitions need it. `<Link viewTransition>` and
 * `useViewTransitionState` are both implemented on the data router's
 * navigation, so under `BrowserRouter` the prop is accepted and silently does
 * nothing — every navigation stays a hard cut and the shared campaign name
 * never travels. Nothing else about the route table changes. */
const router = createBrowserRouter(
  // Every screen sits inside the rail, the console included: leaving a run to
  // change a setting should not mean leaving the machine.
  createRoutesFromElements(
    <Route element={<Shell />} errorElement={<PageError />}>
          <Route path="/account" element={<Account />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/campaigns" element={<Home />} />
          <Route path="/" element={<Home />} />
          {/* A campaign is a hub with two studios under it, and the studios
              are reachable straight from the rail as well — the chooser
              guides, it does not stand in the way. */}
          <Route path="/campaigns/:id" element={<CampaignHub />} />
          <Route path="/campaigns/:id/image" element={<ImageStudio />} />
          <Route path="/campaigns/:id/video/demo" element={<VideoStudio />} />
          <Route path="/campaigns/:id/video" element={<VideoStudio />} />
          <Route
            path="/campaigns/:id/export"
            element={<Navigate to="../publish" relative="path" replace />}
          />
          <Route path="/campaigns/:id/publish" element={<Publish />} />
          <Route path="/studio/image" element={<StudioShortcut medium="image" />} />
          <Route path="/studio/video" element={<StudioShortcut medium="video" />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/brand" element={<BrandProfile />} />
          {/* The Agentcy product explainer keeps its own room: its subject is
              Agentcy itself, not a customer's campaign. */}
          <Route path="/video-studio" element={<Navigate to="/demo-video" replace />} />
          <Route path="/demo-video" element={<DemoVideo />} />
          <Route path="/cinematic-trailer/demo" element={<CinematicTrailer demo />} />
          <Route path="/cinematic-trailer" element={<CinematicTrailer />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/history" element={<History />} />
          <Route path="/progress" element={<Progress />} />
          {/* Export stands on its own as well as under a campaign: the
              finished work is a thing you go and look at, and having to
              remember which campaign made it is not how anyone looks. */}
          <Route path="/export" element={<Navigate to="/publish" replace />} />
          <Route path="/publish" element={<Publish />} />
    </Route>,
  ),
)

export default function App() {
  return (
    <>
      <AuthGate><RouterProvider router={router} /></AuthGate>
      {/* Outside the router: toasts are global and need no route context. */}
      <Toaster position="bottom-right" />
    </>
  )
}
