
interface ConstellabSymbolProps {
  size?: number | string;
  className?: string;
  color?: string;
  glow?: boolean;
}

export function ConstellabSymbol({
  size = 24,
  className = "",
  color = "currentColor",
  glow = false,
}: ConstellabSymbolProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 400 400"
      width={size}
      height={size}
      className={`constellab-symbol ${glow ? "constellab-symbol--glow" : ""} ${className}`}
      fill="none"
      aria-hidden="true"
    >
      {/* Outer circular seal */}
      <circle
        cx="200"
        cy="200"
        r="120"
        fill="none"
        stroke={color}
        strokeWidth="11"
      />
      {/* Hexagonal core */}
      <path
        d="M261 154 L200 125 L139 154 L139 246 L200 275 L261 246"
        fill="none"
        stroke={color}
        strokeWidth="22"
        strokeLinecap="butt"
        strokeLinejoin="miter"
      />
      {/* Continuous orbital ellipse tilted at -34 degrees */}
      <ellipse
        cx="200"
        cy="200"
        rx="170"
        ry="42"
        transform="rotate(-34 200 200)"
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
      />
      {/* Center nucleus */}
      <circle cx="200" cy="200" r="16.5" fill={color} />
    </svg>
  );
}
