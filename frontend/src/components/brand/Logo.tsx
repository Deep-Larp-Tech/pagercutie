import type { SVGProps } from 'react'

/** Mark colours, fixed across themes (DESIGN.md §12): light `--primary` and `--primary-foreground`. */
const TILE = '#6d4ae4'
const FACE = '#fbfbfe'

/** "PagerCutie" in Geist SemiBold, -0.02em, outlined at 40-unit size; cap height 28.4, ink starts at x 3.2. */
const WORDMARK_PATH =
  'M3.2 28.4V0H14.2Q19.16 0 21.98 2.4Q24.8 4.8 24.8 9.04Q24.8 13.32 21.98 15.74Q19.16 18.16 14.2 18.16H8.4V28.4ZM8.4 13.64H13.96Q16.6 13.64 18.02 12.48Q19.44 11.32 19.44 9.04Q19.44 6.8 18.02 5.66Q16.6 4.52 13.96 4.52H8.4ZM33.88 28.88Q30.52 28.88 28.48 27.36Q26.44 25.84 26.44 23.04Q26.44 20.28 28.16 18.72Q29.88 17.16 33.4 16.48L40.48 15.08Q40.48 10.52 36.36 10.52Q34.52 10.52 33.44 11.38Q32.36 12.24 32 13.84L26.8 13.6Q27.44 10.24 29.92 8.4Q32.4 6.56 36.36 6.56Q40.92 6.56 43.26 8.86Q45.6 11.16 45.6 15.44V23.2Q45.6 24.04 45.9 24.36Q46.2 24.68 46.8 24.68H47.48V28.4Q46.8 28.56 45.6 28.56Q43.88 28.56 42.68 27.84Q41.48 27.12 41.16 25.16V25.12Q40.36 26.8 38.42 27.84Q36.48 28.88 33.88 28.88ZM34.92 25.16Q37.48 25.16 38.98 23.68Q40.48 22.2 40.48 19.76V18.56L34.96 19.68Q33.24 20.04 32.5 20.74Q31.76 21.44 31.76 22.56Q31.76 25.16 34.92 25.16ZM58.88 34.88Q54.68 34.88 52.28 33.2Q49.88 31.52 49.16 28.8L54.44 28.44Q54.84 29.68 55.82 30.34Q56.8 31 58.88 31Q61.24 31 62.52 29.94Q63.8 28.88 63.8 26.64V23.92Q63.04 25.48 61.36 26.42Q59.68 27.36 57.6 27.36Q54.96 27.36 52.9 26.06Q50.84 24.76 49.68 22.42Q48.52 20.08 48.52 17Q48.52 13.92 49.68 11.58Q50.84 9.24 52.86 7.9Q54.88 6.56 57.52 6.56Q59.8 6.56 61.48 7.6Q63.16 8.64 63.96 10.36V7.04H68.96V26.52Q68.96 30.64 66.2 32.76Q63.44 34.88 58.88 34.88ZM58.8 23.36Q61.08 23.36 62.46 21.66Q63.84 19.96 63.84 16.96Q63.88 14 62.5 12.28Q61.12 10.56 58.8 10.56Q56.44 10.56 55.14 12.3Q53.84 14.04 53.84 16.96Q53.84 19.88 55.18 21.62Q56.52 23.36 58.8 23.36ZM82.6 28.88Q79.4 28.88 77.04 27.5Q74.68 26.12 73.4 23.6Q72.12 21.08 72.12 17.72Q72.12 14.36 73.4 11.84Q74.68 9.32 77.02 7.94Q79.36 6.56 82.48 6.56Q85.52 6.56 87.8 7.92Q90.08 9.28 91.34 11.84Q92.6 14.4 92.6 18V19.16H77.44Q77.56 21.96 78.96 23.38Q80.36 24.8 82.64 24.8Q86.12 24.8 87.08 21.84L92.32 22.16Q91.44 25.28 88.86 27.08Q86.28 28.88 82.6 28.88ZM77.44 15.72H87.32Q87.12 13.12 85.82 11.86Q84.52 10.6 82.48 10.6Q80.4 10.6 79.08 11.92Q77.76 13.24 77.44 15.72ZM95.8 28.4V7.04H100.6L100.72 11.2Q101.36 9.04 102.6 8.04Q103.84 7.04 105.84 7.04H107.8V11.44H105.8Q103.36 11.44 102.14 12.54Q100.92 13.64 100.92 16.08V28.4ZM123.44 29.04Q119.56 29.04 116.6 27.26Q113.64 25.48 111.96 22.18Q110.28 18.88 110.28 14.24Q110.28 9.68 111.92 6.34Q113.56 3 116.52 1.18Q119.48 -0.64 123.48 -0.64Q128.92 -0.64 131.92 2.06Q134.92 4.76 135.84 9.6L130.4 9.88Q129.88 7.08 128.16 5.48Q126.44 3.88 123.48 3.88Q119.88 3.88 117.76 6.68Q115.64 9.48 115.64 14.24Q115.64 19.04 117.78 21.78Q119.92 24.52 123.44 24.52Q126.6 24.52 128.34 22.78Q130.08 21.04 130.56 18L136 18.28Q135.16 23.28 131.98 26.16Q128.8 29.04 123.44 29.04ZM146 28.88Q142.72 28.88 140.84 26.76Q138.96 24.64 138.96 20.8V7.04H144.08V19.52Q144.08 22.24 144.98 23.48Q145.88 24.72 147.72 24.72Q149.76 24.72 150.92 23.34Q152.08 21.96 152.08 19.32V7.04H157.2V28.4H152.52L152.44 24.92Q150.76 28.88 146 28.88ZM169.68 28.4Q166.48 28.4 164.98 26.94Q163.48 25.48 163.48 22.28V11H160.12V7.04H163.48V2.04H168.6V7.04H174.24V11H168.6V21.8Q168.6 23.32 169.26 23.88Q169.92 24.44 171.24 24.44H174.24V28.4ZM176.88 28.4V7.04H182V28.4ZM176.8 4.2V-0.36H182.12V4.2ZM195.68 28.88Q192.48 28.88 190.12 27.5Q187.76 26.12 186.48 23.6Q185.2 21.08 185.2 17.72Q185.2 14.36 186.48 11.84Q187.76 9.32 190.1 7.94Q192.44 6.56 195.56 6.56Q198.6 6.56 200.88 7.92Q203.16 9.28 204.42 11.84Q205.68 14.4 205.68 18V19.16H190.52Q190.64 21.96 192.04 23.38Q193.44 24.8 195.72 24.8Q199.2 24.8 200.16 21.84L205.4 22.16Q204.52 25.28 201.94 27.08Q199.36 28.88 195.68 28.88ZM190.52 15.72H200.4Q200.2 13.12 198.9 11.86Q197.6 10.6 195.56 10.6Q193.48 10.6 192.16 11.92Q190.84 13.24 190.52 15.72Z'

/** Mark shapes on the 64-unit grid, grouped so animations can target the tile, body, screen and face. */
function MarkShapes() {
  return (
    <>
      <rect className="logo-tile" width="64" height="64" rx="15" fill={TILE} />
      <rect className="logo-body" x="9" y="14" width="46" height="36" rx="10" fill={FACE} />
      <rect className="logo-screen" x="15" y="20" width="34" height="24" rx="4" fill={TILE} />
      <g className="logo-face" fill={FACE}>
        <circle className="logo-eye" cx="25" cy="28.6" r="3.2" />
        <circle className="logo-eye" cx="39" cy="28.6" r="3.2" />
        <path
          className="logo-smile"
          d="M27.5 35.6Q32 39.4 36.5 35.6"
          fill="none"
          stroke={FACE}
          strokeWidth="3"
          strokeLinecap="round"
          pathLength={1}
        />
      </g>
    </>
  )
}

type MarkProps = Omit<SVGProps<SVGSVGElement>, 'viewBox' | 'children'> & {
  /** Rendered width and height in px. */
  size?: number
  /** Accessible name; omit when the mark sits next to visible text. */
  label?: string
}

/** PagerCutie mark: a pager with a face on a violet tile. */
export function LogoMark({ size = 32, label, ...props }: MarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      {...props}
    >
      <MarkShapes />
    </svg>
  )
}

type LogoProps = Omit<SVGProps<SVGSVGElement>, 'viewBox' | 'children'> & {
  /** Rendered height in px; width follows the 255 × 41 aspect ratio. */
  height?: number
}

/** PagerCutie logo: mark plus wordmark. The wordmark takes `currentColor`, so it follows the theme's text colour. */
export function Logo({ height = 32, ...props }: LogoProps) {
  return (
    <svg
      width={(height * 255) / 41}
      height={height}
      viewBox="0 0 255 41"
      role="img"
      aria-label="PagerCutie"
      {...props}
    >
      <g className="logo-mark" transform="scale(0.625)">
        <MarkShapes />
      </g>
      <path className="logo-wordmark" transform="translate(48.8 5.8)" fill="currentColor" d={WORDMARK_PATH} />
    </svg>
  )
}
