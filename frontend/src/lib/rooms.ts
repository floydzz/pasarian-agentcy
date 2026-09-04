import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'

/** How deep into the machine a route sits.
 *
 * The third clause of the motion doctrine says that moving between rooms is a
 * camera move rather than a cut, and a camera move needs a direction. The
 * routes already describe a hierarchy — the directory, then a campaign, then
 * one of its studios — so the direction is not a guess, it is a subtraction.
 *
 * Anything unrecognised sits at the depth of a top-level room, which makes an
 * unknown route a cross-fade rather than a lurch in an arbitrary direction.
 */
export function roomDepth(pathname: string): number {
  if (pathname === '/') return 0

  const segments = pathname.split('/').filter(Boolean)

  // /campaigns/:id is a room; /campaigns/:id/image is a room inside it.
  if (segments[0] === 'campaigns') return segments.length >= 3 ? 2 : 1

  // The studio shortcuts land in a studio, so they are at a studio's depth
  // however few segments they are written with.
  if (segments[0] === 'studio') return 2

  return 1
}

export type RoomDirection = 'forward' | 'back' | 'level'

export function roomDirection(from: string, to: string): RoomDirection {
  const delta = roomDepth(to) - roomDepth(from)
  if (delta > 0) return 'forward'
  if (delta < 0) return 'back'
  return 'level'
}

/** Stamps the direction on `<html>` so the view-transition rules in
 * `index.css` know which way the camera is travelling.
 *
 * It has to happen in the click handler rather than in an effect on the new
 * location: by the time an effect runs the transition has already been
 * captured, and the room would animate in whichever direction the last
 * navigation happened to set.
 */
export function useRoomNav() {
  const { pathname } = useLocation()

  return useCallback(
    (to: string) => {
      document.documentElement.dataset.nav = roomDirection(pathname, to)
    },
    [pathname],
  )
}
