import React from 'react';

interface NanoH2oLogoProps {
  height?: number;
  textColor?: string;
  dotColor?: string;
}

export const NanoH2oLogo: React.FC<NanoH2oLogoProps> = ({
  height = 24,
  textColor = '#ffffff',
  dotColor = '#ff5f1f',
}) => {
  // Exact SVG vector geometry inspired by NANOH2O branding
  return (
    <svg
      height={height}
      viewBox="0 0 460 76"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'inline-block', verticalAlign: 'middle' }}
      aria-label="NANOH2O Logo"
    >
      {/* N 1 */}
      <path
        d="M0 72V4H12.5L37 45.5V4H52V72H39.5L15 30.5V72H0Z"
        fill={textColor}
      />
      {/* Orange dot for N 1 */}
      <rect x="42" y="4" width="16" height="16" fill={dotColor} rx="1.5" />

      {/* A (Chevron Λ) */}
      <path
        d="M72 72L98 4H109L135 72H118L103.5 28L89 72H72Z"
        fill={textColor}
      />

      {/* N 2 */}
      <path
        d="M149 72V4H161.5L186 45.5V4H201V72H188.5L164 30.5V72H149Z"
        fill={textColor}
      />
      {/* Orange dot for N 2 */}
      <rect x="191" y="4" width="16" height="16" fill={dotColor} rx="1.5" />

      {/* O 1 */}
      <path
        d="M246 4C231 4 220 15 220 38C220 61 231 72 246 72C261 72 272 61 272 38C272 15 261 4 246 4ZM246 58C239 58 235 50 235 38C235 26 239 18 246 18C253 18 257 26 257 38C257 50 253 58 246 58Z"
        fill={textColor}
      />

      {/* H */}
      <path
        d="M290 72V4H305V31H329V4H344V72H329V45H305V72H290Z"
        fill={textColor}
      />
      {/* Orange dot for H */}
      <rect x="334" y="4" width="16" height="16" fill={dotColor} rx="1.5" />

      {/* 2 */}
      <path
        d="M362 72V60C362 57 364 54 367 51L391 26C396 21 398 17 398 13C398 8 394 5 388 5C381 5 376 9 375 16H360C361 4 372 -6 388 -6C404 -6 414 4 414 15C414 22 410 29 402 36L384 55H415V72H362Z"
        fill={textColor}
        transform="translate(0, 4)"
      />

      {/* O 2 */}
      <path
        d="M434 4C419 4 408 15 408 38C408 61 419 72 434 72C449 72 460 61 460 38C460 15 449 4 434 4ZM434 58C427 58 423 50 423 38C423 26 427 18 434 18C441 18 445 26 445 38C445 50 441 58 434 58Z"
        fill={textColor}
      />
    </svg>
  );
};
