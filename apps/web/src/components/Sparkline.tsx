// 玩家頁近期走勢小圖：輕量 SVG，不依賴 recharts（避免在清單頁拉進圖表庫）。
interface Props {
  values: number[];
  color?: string;
  width?: number;
  height?: number;
}

export function Sparkline({
  values,
  color = 'var(--color-primary)',
  width = 72,
  height = 28,
}: Props) {
  if (values.length === 0) {
    return <svg width={width} height={height} className="sparkline" aria-hidden />;
  }

  // 把單場金額轉成「累計」走勢，更能反映趨勢
  const cumulative: number[] = [];
  values.reduce((acc, v) => {
    const next = acc + v;
    cumulative.push(next);
    return next;
  }, 0);

  const min = Math.min(0, ...cumulative);
  const max = Math.max(0, ...cumulative);
  const range = max - min || 1;
  const pad = 2;

  const stepX = values.length > 1 ? (width - pad * 2) / (cumulative.length - 1) : 0;
  const points = cumulative.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (1 - (v - min) / range) * (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  // 0 基準線位置
  const zeroY = pad + (1 - (0 - min) / range) * (height - pad * 2);

  return (
    <svg width={width} height={height} className="sparkline" aria-hidden>
      <line
        x1={pad}
        y1={zeroY}
        x2={width - pad}
        y2={zeroY}
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      {points.length === 1 ? (
        <circle cx={points[0].split(',')[0]} cy={points[0].split(',')[1]} r={2} fill={color} />
      ) : (
        <polyline
          points={points.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
