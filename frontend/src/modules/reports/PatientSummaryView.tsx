import { useState, type CSSProperties, type ReactNode } from "react";
import { Badge, Callout, Card, Flex, Grid, Heading, Skeleton, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import {
  usePatientOverview,
  usePatientSummary,
  usePatientTrends,
  usePatientVersions,
  type AbnormalFinding,
  type AbnormalSeverity,
  type AreaSummary,
  type Contributor,
  type CriticalityLevel,
  type Highlight,
  type KeyPoint,
  type PatientSummary,
} from "../patients/api";
import { useReconciliations } from "../reconciliation/api";
import { TrendList } from "./TrendList";
import { professionLabel } from "../recordings/professions";
import { sectionLabel } from "../templates/recordFields";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });
const SEVERITY_COLOR: Record<string, "red" | "amber" | "gray"> = { alta: "red", media: "amber" };
const CRITICALITY_COLOR: Record<CriticalityLevel, "red" | "orange" | "amber" | "green"> = {
  critical: "red",
  high: "orange",
  moderate: "amber",
  stable: "green",
};

interface PatientSummaryViewProps {
  patientId: number;
  /** Apartado que va entre las secciones de estado y «Más información». */
  assistant?: ReactNode;
}

type Tone = "blue" | "indigo" | "red" | "amber" | "cyan" | "violet" | "green" | "gray";

/** Resumen único del paciente: resumen, áreas, valores fuera de rango, tareas y más información. */
export function PatientSummaryView({ patientId, assistant }: PatientSummaryViewProps) {
  const { data: summary, isPending, isError, error } = usePatientSummary(patientId);
  const { data: overview } = usePatientOverview(patientId);
  const { data: trends = [] } = usePatientTrends(patientId);
  const { data: reconciliations = [] } = useReconciliations();

  if (isError) {
    return (
      <Callout.Root color="red">
        <Callout.Text>No se pudo cargar el resumen: {error.message}</Callout.Text>
      </Callout.Root>
    );
  }
  if (isPending) return <Skeleton height="160px" />;
  if (summary.reportCount === 0) {
    return (
      <Text size="2" color="gray">
        Este paciente aún no tiene informes guardados. Graba un dictado, valida sus temas y guarda el informe para ver el resumen.
      </Text>
    );
  }

  const conflicts = reconciliations
    .filter((item) => item.patientId === patientId)
    .flatMap((item) => item.conflicts)
    .filter((conflict) => conflict.status === "open");
  const tasks = (group: string) => summary.treatmentPending.filter((item) => item.group === group);
  const groups = groupHighlights(summary.highlights);

  return (
    <Flex direction="column" gap="4">
      <SummaryCard summary={summary} globalSummary={overview?.globalSummary} contributors={overview?.contributors} />

      <Panel title="Información por áreas" tone="indigo" detail="Síntesis de lo consolidado, por área clínica">
        {!overview ? (
          <Skeleton height="120px" />
        ) : overview.areas.length === 0 ? (
          <Text size="2" color="gray">
            Todavía no hay información para organizar por áreas.
          </Text>
        ) : (
          <Grid columns={{ initial: "1", sm: "2" }} gap="3">
            {overview.areas.map((area) => (
              <AreaCard
                key={area.area}
                area={area}
                conflictCount={conflicts.filter((conflict) => area.sections.includes(conflict.section)).length}
              />
            ))}
          </Grid>
        )}
      </Panel>

      <Panel
        title="Métricas fuera de rango"
        tone="red"
        count={summary.abnormal.length}
        detail="Primero lo más grave y lo ligado a mortalidad"
      >
        {summary.abnormal.length === 0 ? (
          <Text size="2" color="gray">
            Sin exámenes ni escalas fuera de rango.
          </Text>
        ) : (
          <Flex direction="column" gap="2">
            {summary.abnormal.map((finding) => (
              <AbnormalRow key={`${finding.kind}-${finding.name}`} finding={finding} />
            ))}
          </Flex>
        )}
      </Panel>

      <TaskPanel title="Planes pendientes" tone="amber" items={tasks("Pendientes")} patientId={patientId} empty="Sin pendientes registrados." emphasized />
      <TaskPanel title="Indicaciones" tone="cyan" items={tasks("Indicaciones")} patientId={patientId} empty="Sin indicaciones registradas." />
      <TaskPanel title="Recomendaciones" tone="violet" items={tasks("Recomendaciones")} patientId={patientId} empty="Sin recomendaciones registradas." />
      <TaskPanel title="Metas del día" tone="green" items={tasks("Metas del día")} patientId={patientId} empty="Sin metas registradas." />

      <Panel
        title="Tendencias"
        tone="blue"
        count={trends.length}
        detail="Evolución de exámenes y escalas para orientar el juicio clínico"
      >
        {trends.length === 0 ? (
          <Text size="2" color="gray">
            Aún no hay dos o más mediciones de un mismo examen o escala para mostrar su evolución.
          </Text>
        ) : (
          <TrendList trends={trends} />
        )}
      </Panel>

      {assistant}

      <Heading size="3" mt="2">
        Más información
      </Heading>
      <Text size="1" color="gray" mt="-2">
        Versión oficial n.º {summary.version}: el resumen sale de lo ya consolidado entre los profesionales.
      </Text>

      {groups.map(([group, items]) => (
        <CollapsibleSection key={group} title={group} detail={String(items.length)}>
          <Flex direction="column" gap="2">
            {items.map((item, index) => (
              <HighlightRow key={`${item.reportId}-${item.section}-${index}`} item={item} patientId={patientId} />
            ))}
          </Flex>
        </CollapsibleSection>
      ))}

      <VersionHistory patientId={patientId} />

      <CollapsibleSection
        title="Informes por profesional"
        detail={`${summary.reportCount} ${summary.reportCount === 1 ? "informe" : "informes"}`}
      >
        <Flex direction="column" gap="2">
          {summary.byProfession.map((activity) => (
            <Flex key={activity.profession} justify="between" align="center" gap="3" wrap="wrap">
              <Flex direction="column">
                <Text size="2" weight="medium">
                  {professionLabel(activity.profession)} · {activity.count}
                </Text>
                <Text size="1" color="gray">
                  Último: {activity.lastAuthor} · {DATE_FORMAT.format(new Date(activity.lastAt))}
                </Text>
              </Flex>
              <Link
                to="/"
                search={{ patient: String(patientId), report: activity.lastReportId }}
                style={{ fontSize: "var(--font-size-1)" }}
              >
                Abrir el último informe
              </Link>
            </Flex>
          ))}
        </Flex>
      </CollapsibleSection>
    </Flex>
  );
}

interface PanelProps {
  title: string;
  tone: Tone;
  detail?: string;
  count?: number;
  /** Se puede minimizar (por defecto sí; arranca abierto). */
  collapsible?: boolean;
  children: ReactNode;
}

/** Bloque con encabezado de color: separa con claridad cada área de datos. */
function Panel({ title, tone, detail, count, collapsible = true, children }: PanelProps) {
  const [expanded, setExpanded] = useState(true);
  const open = !collapsible || expanded;
  const header = (
    <Flex align="center" justify="between" gap="3" wrap="wrap" style={{ width: "100%" }}>
      <Flex align="center" gap="2">
        {collapsible && (
          <Text aria-hidden="true" color={tone} style={{ width: 14 }}>
            {expanded ? "▾" : "▸"}
          </Text>
        )}
        <Heading size="3">{title}</Heading>
        {count !== undefined && (
          <Badge color={count > 0 ? tone : "gray"} variant={count > 0 ? "solid" : "soft"} radius="full">
            {count}
          </Badge>
        )}
      </Flex>
      {detail && (
        <Text size="1" color="gray">
          {detail}
        </Text>
      )}
    </Flex>
  );
  return (
    <section
      style={{
        border: `1px solid var(--${tone}-a6)`,
        borderTop: `4px solid var(--${tone}-9)`,
        borderRadius: "var(--radius-3)",
        overflow: "hidden",
        background: "var(--color-panel-solid)",
      }}
    >
      {collapsible ? (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          style={panelHeaderStyle(tone, open)}
        >
          {header}
        </button>
      ) : (
        <div style={panelHeaderStyle(tone, open)}>{header}</div>
      )}
      {open && <div style={{ padding: "var(--space-3)" }}>{children}</div>}
    </section>
  );
}

function panelHeaderStyle(tone: Tone, open: boolean): CSSProperties {
  return {
    display: "block",
    width: "100%",
    padding: "var(--space-3)",
    border: 0,
    borderBottom: open ? `1px solid var(--${tone}-a5)` : 0,
    background: `var(--${tone}-a3)`,
    textAlign: "left",
    font: "inherit",
    color: "inherit",
    cursor: "default",
  };
}

interface TaskPanelProps {
  title: string;
  tone: Tone;
  items: Highlight[];
  patientId: number;
  empty: string;
  emphasized?: boolean;
}

function TaskPanel({ title, tone, items, patientId, empty, emphasized = false }: TaskPanelProps) {
  return (
    <Panel title={title} tone={tone} count={items.length}>
      {items.length === 0 ? (
        <Text size="2" color="gray">
          {empty}
        </Text>
      ) : (
        <Flex direction="column" gap="3">
          {items.map((item, index) => (
            <HighlightRow
              key={`${item.reportId}-${item.section}-${index}`}
              item={item}
              patientId={patientId}
              emphasized={emphasized}
            />
          ))}
        </Flex>
      )}
    </Panel>
  );
}

const SEVERITY_TONE: Record<AbnormalSeverity, "red" | "orange" | "amber"> = {
  critical: "red",
  high: "orange",
  moderate: "amber",
};

function AbnormalRow({ finding }: { finding: AbnormalFinding }) {
  const tone = SEVERITY_TONE[finding.severity];
  const strong = finding.severity === "critical";
  return (
    <Flex
      align="center"
      justify="between"
      gap="3"
      wrap="wrap"
      p="2"
      style={{
        background: strong ? `var(--${tone}-a3)` : "var(--gray-a2)",
        borderLeft: `4px solid var(--${tone}-9)`,
        borderRadius: "var(--radius-2)",
      }}
    >
      <Flex direction="column" gap="1">
        <Flex align="center" gap="2" wrap="wrap">
          <Text size={strong ? "3" : "2"} weight="bold">
            {finding.name}
          </Text>
          <Badge color={tone} variant={strong ? "solid" : "soft"}>
            {finding.severityLabel}
          </Badge>
          {finding.mortality && (
            <Badge color="crimson" variant="outline">
              Mortalidad
            </Badge>
          )}
          <Badge color="gray" variant="surface">
            {finding.kind === "scale" ? "Escala" : "Laboratorio"}
          </Badge>
        </Flex>
        <Text size="1" color="gray">
          {finding.note}
          {finding.reference ? ` · referencia ${finding.reference}` : ""}
          {finding.at ? ` · ${DATE_FORMAT.format(new Date(finding.at))}` : ""}
        </Text>
      </Flex>
      <Text size={strong ? "5" : "4"} weight="bold" color={tone}>
        {finding.value}
        {finding.unit && (
          <Text size="1" color="gray" weight="regular">
            {" "}
            {finding.unit}
          </Text>
        )}
      </Text>
    </Flex>
  );
}

function SummaryCard({
  summary,
  globalSummary,
  contributors,
}: {
  summary: PatientSummary;
  globalSummary?: string;
  contributors?: Contributor[];
}) {
  const { criticality } = summary;
  const text = globalSummary || summary.brief;
  return (
    <Card variant="classic" style={{ borderLeft: `4px solid var(--${CRITICALITY_COLOR[criticality.level]}-9)` }}>
      <Flex direction="column" gap="3">
        <Heading size="3">Resumen</Heading>
        <Flex align="center" gap="3" wrap="wrap">
          <Badge size="3" color={CRITICALITY_COLOR[criticality.level]} variant="solid">
            Criticidad: {criticality.label}
          </Badge>
          {summary.status && <Text size="2">{summary.status}</Text>}
        </Flex>
        {text && (
          <Text size="3" style={{ lineHeight: 1.6 }}>
            {text}
          </Text>
        )}
        <KeyPoints points={summary.keyPoints} />
        {criticality.reasons.length > 0 && (
          <Flex gap="2" wrap="wrap">
            {criticality.reasons.map((reason) => (
              <Badge key={reason} color="gray" variant="surface">
                {reason}
              </Badge>
            ))}
          </Flex>
        )}
        {contributors && contributors.length > 0 && (
          <Flex align="center" gap="2" wrap="wrap">
            <Text size="1" color="gray">
              Aportaron informes:
            </Text>
            {contributors.map((contributor) => (
              <Badge key={contributor.profession} color={contributor.inConflict ? "orange" : "indigo"} variant="soft">
                {professionLabel(contributor.profession)}
                {contributor.reportCount > 1 && ` · ${contributor.reportCount} informes`}
                {contributor.inConflict && " · en conflicto"}
              </Badge>
            ))}
          </Flex>
        )}
      </Flex>
    </Card>
  );
}

/** Lo que hay que saber antes de actuar: LET, no RCP, limitaciones y alergias. */
function KeyPoints({ points }: { points: KeyPoint[] }) {
  if (points.length === 0) return null;
  return (
    <Flex direction="column" gap="2" p="3" style={{ background: "var(--gray-a2)", borderRadius: "var(--radius-3)" }}>
      <Text size="1" weight="bold" color="gray" style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
        Puntos importantes
      </Text>
      {points.map((point) => (
        <Flex key={`${point.kind}-${point.label}`} align="center" gap="2" wrap="wrap">
          <Badge
            size="2"
            color={point.tone}
            variant={point.tone === "red" || point.tone === "orange" ? "solid" : "soft"}
          >
            {point.label}
          </Badge>
          {point.detail && (
            <Text size="2" color="gray">
              {point.detail}
            </Text>
          )}
        </Flex>
      ))}
    </Flex>
  );
}

function AreaCard({ area, conflictCount }: { area: AreaSummary; conflictCount: number }) {
  return (
    <Card variant="surface" style={conflictCount > 0 ? { borderLeft: "4px solid var(--orange-9)" } : undefined}>
      <Flex direction="column" gap="2">
        <Flex justify="between" align="center" gap="2">
          <Text weight="medium">{area.area}</Text>
          <Flex gap="2">
            {conflictCount > 0 && (
              <Badge color="orange" variant="solid">
                {conflictCount === 1 ? "En conflicto" : `${conflictCount} en conflicto`}
              </Badge>
            )}
            {!area.informed && (
              <Badge color="amber" variant="soft">
                Sin información
              </Badge>
            )}
          </Flex>
        </Flex>
        <Text size="2" color={area.informed ? undefined : "gray"} style={{ lineHeight: 1.5 }}>
          {area.informed
            ? area.summary || "Hay datos registrados, pero aún sin síntesis."
            : "Aún no se ha registrado nada en esta área."}
        </Text>
        {area.contributors.length > 0 && (
          <Flex align="center" gap="1" wrap="wrap">
            <Text size="1" color="gray">
              Aportó:
            </Text>
            {area.contributors.map((profession) => (
              <Badge key={profession} color="gray" variant="surface" size="1">
                {professionLabel(profession)}
              </Badge>
            ))}
          </Flex>
        )}
      </Flex>
    </Card>
  );
}

function HighlightRow({
  item,
  patientId,
  showGroup = false,
  emphasized = false,
}: {
  item: Highlight;
  patientId: number;
  showGroup?: boolean;
  emphasized?: boolean;
}) {
  return (
    <Flex justify="between" align="center" gap="3" wrap="wrap">
      <Flex align="center" gap="2" style={{ minWidth: 0 }}>
        {showGroup && (
          <Badge color="gray" variant="soft" size="1">
            {item.group}
          </Badge>
        )}
        {item.severity && (
          <Badge color={SEVERITY_COLOR[item.severity] ?? "gray"} variant="soft" size="1">
            {item.severity}
          </Badge>
        )}
        <Text size={emphasized ? "3" : "2"} weight={emphasized ? "bold" : "regular"}>
          {item.text}
        </Text>
      </Flex>
      <Link
        to="/"
        search={{ patient: String(patientId), report: item.reportId, section: item.section }}
        style={{ fontSize: "var(--font-size-1)", whiteSpace: "nowrap" }}
        title={`Informe de ${item.authorName}`}
      >
        {professionLabel(item.profession)} · {sectionLabel(item.section)}
      </Link>
    </Flex>
  );
}

function groupHighlights(highlights: Highlight[]): [string, Highlight[]][] {
  const groups = new Map<string, Highlight[]>();
  for (const highlight of highlights) {
    groups.set(highlight.group, [...(groups.get(highlight.group) ?? []), highlight]);
  }
  return [...groups.entries()];
}

const REASON_LABEL = {
  official: "Primer informe guardado",
  merge: "Informe sin conflictos incorporado",
  reconciliation: "Conflictos resueltos entre profesionales",
} as const;

/** Todas las versiones oficiales del paciente: la vigente y las anteriores, que no se pierden. */
export function VersionHistory({ patientId }: { patientId: number }) {
  const { data: versions = [] } = usePatientVersions(patientId);
  return (
    <CollapsibleSection title="Historial de versiones" detail={`${versions.length} ${versions.length === 1 ? "versión" : "versiones"}`}>
      <Flex direction="column" gap="2">
        {versions.map((version) => (
          <Flex key={version.version} justify="between" align="center" gap="3" wrap="wrap">
            <Flex align="center" gap="2" wrap="wrap">
              <Badge color={version.isCurrent ? "green" : "gray"} variant="soft">
                Versión {version.version}
                {version.isCurrent ? " · vigente" : ""}
              </Badge>
              <Text size="2">{REASON_LABEL[version.reason]}</Text>
            </Flex>
            <Text size="1" color="gray">
              {version.sourceAuthor && `${version.sourceAuthor} · `}
              {DATE_FORMAT.format(new Date(version.created_at))}
            </Text>
          </Flex>
        ))}
      </Flex>
    </CollapsibleSection>
  );
}
