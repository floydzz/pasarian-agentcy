import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { Shell } from '@/components/os/Shell'
import { Agents } from '@/pages/Agents'
import { Console } from '@/pages/Console'
import { History } from '@/pages/History'
import { Home } from '@/pages/Home'
import { Trends } from '@/pages/Trends'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Every screen sits inside the rail, the console included: leaving a
            run to change a setting should not mean leaving the machine. */}
        <Route element={<Shell />}>
          <Route path="/" element={<Home />} />
          <Route path="/campaigns/:id" element={<Console />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/history" element={<History />} />
        </Route>
      </Routes>
      <Toaster position="bottom-right" />
    </BrowserRouter>
  )
}
