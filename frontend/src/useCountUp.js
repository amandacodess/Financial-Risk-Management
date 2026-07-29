import { useEffect, useRef, useState } from 'react'

const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

// Counts up to a figure once, so the headline number lands rather than simply
// being there. Readers who have asked for less motion get the final value.
export function useCountUp(value, duration = 800) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? value : 0))
  const from = useRef(0)

  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(value)
      from.current = value
      return
    }

    const origin = from.current
    const start = performance.now()
    let frame

    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      // The same ease-out the bars use, so everything settles together.
      setShown(origin + (value - origin) * (1 - Math.pow(1 - t, 3)))
      if (t < 1) {
        frame = requestAnimationFrame(tick)
      } else {
        from.current = value
      }
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, duration])

  return shown
}
