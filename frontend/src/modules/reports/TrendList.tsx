import { Badge, Flex, Text } from "@radix-ui/themes";
import type { Trend, TrendStatus } from "../patients/api";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const STATUS: Record<TrendStatus, { label: string; color: "red" | "green" | "gray" | "indigo"; arrow: string }> = {
  worsening: { label: "Empeora", color: "red", arrow: "↘" },
  improving: { label: "Mejora", color: "green", arrow: "↗" },
  stable: { label: "Estable", color: "gray", arrow: "→" },
  neutral: { label: "Cambia", color: "indigo", arrow: "↔" },
};

/** Tendencias de exámenes y escalas: cada una con su gráfico, el cambio y hacia dónde va. */
export function TrendList({ trends }: { trends: Trend[] }) {
  return (
    <Flex direction="column" gap="2">
      {trends.map((trend) => (
        <TrendRow key={`${trend.kind}-${trend.name}`} trend={trend} />
      ))}
    </Flex>
  );
}

function TrendRow({ trend }: { trend: Trend }) {
  const status = STATUS[trend.status];
  const first = trend.points[0];
  const last = trend.points[trend.points.length - 1];
  const sign = trend.change > 0 ? "+" : "";
  return (
    <Flex
      align="center"
      justify="between"
      gap="3"
      wrap="wrap"
      p="2"
      style={{ background: "var(--gray-a2)", borderLeft: `4px solid var(--${status.color}-9)`, borderRadius: "var(--radius-2)" }}
    >
      <Flex direction="column" gap="1" style={{ minWidth: 150 }}>
        <Flex align="center" gap="2" wrap="wrap">
          <Text size="2" weight="bold">
            {trend.name}
          </Text>
          <Badge color={status.color} variant="soft">
            {status.arrow} {status.label}
          </Badge>
          {trend.mortality && (
            <Badge color="crimson" variant="outline">
              Mortalidad
            </Badge>
          )}
        </Flex>
        <Text size="1" color="gray">
          {trend.kind === "scale" ? "Escala" : "Laboratorio"} · {trend.points.length} mediciones ·{" "}
          {DATE_FORMAT.format(new Date(first.at))} → {DATE_FORMAT.format(new Date(last.at))}
        </Text>
      </Flex>
      <Sparkline trend={trend} color={status.color} />
      <Flex direction="column" align="end">
        <Text size="4" weight="bold" color={status.color}>
          {last.value}
          {trend.unit && (
            <Text size="1" color="gray" weight="regular">
              {" "}
              {trend.unit}
            </Text>
          )}
        </Text>
        <Text size="1" color="gray">
          {first.value} → {last.value} ({sign}
          {trend.change})
        </Text>
      </Flex>
    </Flex>
  );
}

const WIDTH = 140;
const HEIGHT = 44;
const PAD = 5;

/** Línea simple de la serie, con la banda del rango de referencia cuando existe. */
function Sparkline({ trend, color }: { trend: Trend; color: string }) {
  const values = trend.points.map((point) => point.value);
  const times = trend.points.map((point) => Date.parse(point.at));
  const band = [trend.refMin, trend.refMax].filter((value): value is number => value !== null);
  const lo = Math.min(...values, ...band);
  const hi = Math.max(...values, ...band);
  const spanY = hi - lo || 1;
  const spanX = Math.max(...times) - Math.min(...times) || 1;
  const x = (time: number) => PAD + ((time - Math.min(...times)) / spanX) * (WIDTH - 2 * PAD);
  const y = (value: number) => HEIGHT - PAD - ((value - lo) / spanY) * (HEIGHT - 2 * PAD);
  const path = trend.points.map((point, index) => `${index ? "L" : "M"}${x(Date.parse(point.at))},${y(point.value)}`).join(" ");
  const top = trend.refMax !== null ? y(trend.refMax) : PAD;
  const bottom = trend.refMin !== null ? y(trend.refMin) : HEIGHT - PAD;
  const lastPoint = trend.points[trend.points.length - 1];

  return (
    <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`Tendencia de ${trend.name}`}>
      {band.length > 0 && (
        <rect x={0} y={top} width={WIDTH} height={Math.max(bottom - top, 1)} fill="var(--green-a3)" />
      )}
      <path d={path} fill="none" stroke={`var(--${color}-9)`} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {trend.points.map((point) => (
        <circle key={point.at} cx={x(Date.parse(point.at))} cy={y(point.value)} r={2.5} fill={`var(--${color}-9)`} />
      ))}
      <circle cx={x(Date.parse(lastPoint.at))} cy={y(lastPoint.value)} r={4} fill={`var(--${color}-9)`} />
    </svg>
  );
}
