import { useCallback, useState } from 'react'
import { cn } from '@/lib/utils'

/** A generated image, arriving.
 *
 * The product's entire output is imagery the machine made, so the frame in
 * which it resolves is the payoff and deserves to be designed. Everywhere else
 * in the instrument, motion means work is moving; here it means work has
 * *landed*, which is the one thing a person waited through a pipeline to see.
 *
 * It develops rather than fades: over-scaled, blurred, desaturated and dim,
 * coming to rest at its true size and full colour — an exposure resolving, not
 * a box being filled in.
 *
 * Two details that are the whole reason this is a component and not a class
 * on five separate `<img>` tags:
 *
 * 1. The animation is driven by the image's `load` event, never by mount. A
 *    mount-triggered reveal animates an empty box and then pops the picture in
 *    at the end, which is precisely backwards.
 * 2. The animation lives on a wrapper, not on the image. `History` scales its
 *    images on hover, and an animation with `both` fill on the image itself
 *    would hold `scale(1)` forever and silently kill that hover for the life
 *    of the page.
 */
export function Plate({
  src,
  alt,
  className,
  frameClassName,
  loading = 'lazy',
  latent = false,
}: {
  src: string
  alt: string
  /** Classes for the image itself: aspect, fit, and any hover behaviour. */
  className?: string
  /** Classes for the frame the image develops inside. */
  frameClassName?: string
  loading?: 'lazy' | 'eager'
  /** Force the plate back to unexposed while the caller remakes the image. */
  latent?: boolean
}) {
  const [loaded, setLoaded] = useState<'latent' | 'developed' | 'failed'>('latent')
  const state = latent ? 'latent' : loaded

  // A redo points the same card at a new file. The plate has to go back to
  // being unexposed, or the second render arrives with no ceremony at all and
  // the most expensive thing the machine does looks like a cache hit.
  //
  // Adjusted during render rather than in an effect: an effect would let one
  // frame of the previous image paint at full opacity underneath the new one.
  const [shown, setShown] = useState(src)
  if (src !== shown) {
    setShown(src)
    setLoaded('latent')
  }

  // A cached image can finish decoding before React attaches the handler, so
  // the element is asked directly rather than waited on.
  const measure = useCallback((node: HTMLImageElement | null) => {
    if (node?.complete && node.naturalWidth > 0) setLoaded('developed')
  }, [])

  return (
    <span className={cn('relative block overflow-hidden', frameClassName)}>
      {/* The unexposed ground. Achromatic, per the one colour rule: a plate
          that has not arrived yet is not reporting a state, so it has no hue
          to report one with. */}
      <span
        aria-hidden
        className={cn(
          'pointer-events-none absolute inset-0 bg-[rgba(233,238,247,0.04)] transition-opacity duration-500',
          state === 'latent' ? 'opacity-100' : 'opacity-0',
        )}
      />

      <span
        className={cn(
          'block h-full w-full',
          state === 'developed' && 'plate-develop',
          state === 'latent' && 'opacity-0',
        )}
      >
        <img
          ref={measure}
          src={src}
          alt={alt}
          loading={loading}
          decoding="async"
          onLoad={() => setLoaded('developed')}
          onError={() => setLoaded('failed')}
          className={className}
        />
      </span>

      {state === 'failed' && (
        <span className="absolute inset-0 flex items-center justify-center px-3 text-center text-[0.6875rem] text-text-3">
          This image could not be loaded.
        </span>
      )}
    </span>
  )
}
