import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { Shell } from '@/components/os/Shell'
import { Agents } from '@/pages/Agents'
import { BrandProfile } from '@/pages/BrandProfile'
import { CampaignHub } from '@/pages/CampaignHub'
import { CinematicTrailer } from '@/pages/CinematicTrailer'
import { DemoVideo } from '@/pages/DemoVideo'
import { History } from '@/pages/History'
import { Home } from '@/pages/Home'
import { ImageStudio } from '@/pages/studio/ImageStudio'
import { StudioShortcut } from '@/pages/studio/StudioShortcut'
import { Trends } from '@/pages/Trends'
import { VideoStudio } from '@/pages/studio/VideoStudio'
import { Progress } from '@/pages/Progress'
import { Publish } from '@/pages/Publish'

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
    <Route element={<Shell />}>
          <Route path="/chat" element={<Navigate to="/?chat=open" replace />} />
          <Route path="/" element={<Home />} />
          {/* A campaign is a hub with two studios under it, and the studios
              are reachable straight from the rail as well — the chooser
              guides, it does not stand in the way. */}
          <Route path="/campaigns/:id" element={<CampaignHub />} />
          <Route path="/campaigns/:id/image" element={<ImageStudio />} />
          <Route path="/campaigns/:id/video" element={<VideoStudio />} />
          <Route path="/campaigns/:id/export" element={<Navigate to="publish" replace />} />
          <Route path="/campaigns/:id/publish" element={<Publish />} />
          <Route path="/studio/image" element={<StudioShortcut medium="image" />} />
          <Route path="/studio/video" element={<StudioShortcut medium="video" />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/brand" element={<BrandProfile />} />
          {/* The Agentcy product explainer keeps its own room: its subject is
              Agentcy itself, not a customer's campaign. */}
          <Route path="/video-studio" element={<Navigate to="/demo-video" replace />} />
          <Route path="/demo-video" element={<DemoVideo />} />
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
      <RouterProvider router={router} />
      {/* Outside the router: toasts are global and need no route context. */}
      <Toaster position="bottom-right" />
    </>
  )
}
