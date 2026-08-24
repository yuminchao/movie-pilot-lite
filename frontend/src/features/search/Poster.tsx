import { useState } from 'react'
import { ImageOff } from 'lucide-react'

interface PosterProps {
  src: string | null
  title: string
  size: 'thumb' | 'detail'
}

export function Poster(props: PosterProps) {
  return <PosterImage key={props.src ?? 'missing'} {...props} />
}

function PosterImage({ src, title, size }: PosterProps) {
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div
        className={`poster poster-${size} poster-fallback`}
        data-testid="poster-fallback"
        role={size === 'detail' ? 'img' : undefined}
        aria-label={size === 'detail' ? `${title} 海报不可用` : undefined}
        aria-hidden={size === 'thumb' ? true : undefined}
      >
        <ImageOff aria-hidden="true" size={size === 'thumb' ? 18 : 30} />
      </div>
    )
  }

  return (
    <img
      className={`poster poster-${size}`}
      src={src}
      alt={`${title} 海报`}
      aria-hidden={size === 'thumb' ? true : undefined}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  )
}
