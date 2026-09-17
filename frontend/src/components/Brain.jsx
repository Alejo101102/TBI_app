const Brain = ({ size = 60, color = 'currentColor', glow = false }) => (
  <svg
    width={size}
    height={Math.round(size * 0.87)}
    viewBox="0 0 100 87"
    fill="none"
    style={{ display: 'block', ...(glow ? { animation: 'glow 3s ease infinite' } : {}) }}
  >
    <path d="M48 10 C34 10 13 17 10 33 C7 49 17 69 31 73 C39 76 45 73 48 70 L48 10Z" fill={color} opacity=".9" />
    <path d="M52 10 C66 10 87 17 90 33 C93 49 83 69 69 73 C61 76 55 73 52 70 L52 10Z" fill={color} opacity=".76" />
    <line x1="50" y1="10" x2="50" y2="70" stroke="white" strokeWidth="2.5" />
    <path d="M15 27 Q26 20 37 26" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    <path d="M12 41 Q24 34 38 40" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    <path d="M13 55 Q25 48 37 54" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    <path d="M85 27 Q74 20 63 26" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    <path d="M88 41 Q76 34 62 40" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    <path d="M87 55 Q75 48 63 54" stroke="white" strokeWidth="1.8" strokeLinecap="round" fill="none" />
  </svg>
);

export default Brain;
