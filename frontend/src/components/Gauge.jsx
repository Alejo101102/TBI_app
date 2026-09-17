const Gauge = ({ value, color, size = 190 }) => {
  const r = 74;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - value / 100);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="oklch(0.93 0.03 240)" strokeWidth="14" />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="14"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(.22,.68,0,1.2)' }}
      />
      <text
        x={cx}
        y={cy - 10}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ fontSize: '36px', fontWeight: 800, fill: color, fontFamily: 'Outfit,sans-serif' }}
      >
        {value}%
      </text>
      <text
        x={cx}
        y={cy + 22}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ fontSize: '12px', fill: 'oklch(0.60 0.03 240)', fontFamily: 'Outfit,sans-serif' }}
      >
        confianza
      </text>
    </svg>
  );
};

export default Gauge;
