import { useState, type ReactNode } from "react";
import { Badge, Box, Button, Callout, Card, Flex, Heading, Link as ThemeLink, Skeleton, Spinner, Tabs, Text, VisuallyHidden } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import {
  usePatientOverview,
  usePatientSummary,
  usePatientTrends,
  usePatientVersions,
  type AbnormalFinding,
  type AbnormalSeverity,
  type AreaSummary,
  type Highlight,
  type KeyPoint,
  type PatientOverview,
  type PatientSummary,
} from "../patients/api";
import { useReconciliations, type Conflict } from "../reconciliation/api";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { AgentCouncil } from "../panel/AgentCouncil";
import { useEvidence } from "../evidence/api";
import { VersionChanges } from "./ReportChanges";
import { TrendList } from "./TrendList";
import { reportTitle } from "./format";
import type { Report } from "./api";
import { professionLabel } from "../recordings/professions";
import { sectionLabel } from "../templates/recordFields";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });
const CARE_SECTIONS = [
  {
    id: "short-term-orders",
    title: "Indicaciones",
    horizon: "Corto plazo",
    empty: "Sin indicaciones, pendientes ni metas del día registradas.",
    groups: [
      { title: "Órdenes", sections: ["indicaciones"] },
      { title: "Pendientes", sections: ["pendientes"] },
      { title: "Metas del día", sections: ["metas_del_dia"] },
    ],
  },
  {
    id: "follow-up-plan",
    title: "Plan",
    horizon: "Mediano y largo plazo",
    empty: "Sin objetivos terapéuticos ni recomendaciones registrados.",
    groups: [
      { title: "Objetivos terapéuticos", sections: ["objetivos_terapeuticos"] },
      { title: "Recomendaciones", sections: ["recomendaciones_al_tratante", "recomendaciones_equipo"] },
    ],
  },
];
const GLANCE_LIMIT = 3;
const PLAN_AREA = "Plan y pendientes";

export type PatientTab = "summary" | "plan" | "exams" | "history";

interface PatientSummaryViewProps {
  patientId: number;
  /** Informes guardados del paciente (Historial). */
  reports: Report[];
  reportsLoading?: boolean;
  onOpenReport: (reportId: string) => void;
  tab: PatientTab;
  onTabChange: (tab: PatientTab) => void;
  /** Apartado opcional al final del Resumen (p. ej. un asistente embebido). */
  assistant?: ReactNode;
}

/** Ficha del paciente en pestañas: Resumen · Indicaciones y plan · Exámenes · Historial. */
export function PatientSummaryView({ patientId, reports, reportsLoading = false, onOpenReport, tab, onTabChange, assistant }: PatientSummaryViewProps) {
  const { data: summary, isError, error } = usePatientSummary(patientId);
  const { data: overview, isPending: overviewPending } = usePatientOverview(patientId);

  const planCount = summary?.treatmentPending.length ?? 0;
  const examCount = summary?.abnormal.length ?? 0;
  const needsSummary = (content: (summary: PatientSummary) => ReactNode) =>
    summary ? (
      content(summary)
    ) : isError ? (
      <Callout.Root color="red" variant="surface">
        <Callout.Text>No se pudo cargar el resumen: {error.message}</Callout.Text>
      </Callout.Root>
    ) : (
      <Skeleton height="160px" />
    );

  return (
    <Tabs.Root value={tab} onValueChange={(value) => onTabChange(value as PatientTab)}>
      <Box overflowX="auto">
        <Tabs.List size="2" aria-label="Información del paciente">
          <Tabs.Trigger value="summary">Resumen</Tabs.Trigger>
          <Tabs.Trigger value="plan">
            Indicaciones y plan
            <TabCount value={planCount} label={planCount === 1 ? "registro" : "registros"} />
          </Tabs.Trigger>
          <Tabs.Trigger value="exams">
            Exámenes
            <TabCount value={examCount} label={examCount === 1 ? "hallazgo fuera de rango" : "hallazgos fuera de rango"} />
          </Tabs.Trigger>
          <Tabs.Trigger value="history">Historial</Tabs.Trigger>
        </Tabs.List>
      </Box>

      <Box pt="4">
        <Tabs.Content value="summary">
          {needsSummary((data) => (
            <SummaryTab
              summary={data}
              overview={overview}
              overviewPending={overviewPending}
              patientId={patientId}
              onTab={onTabChange}
              assistant={assistant}
            />
          ))}
          <Box pt="4">
            <AgentCouncil patientId={patientId} canLaunch />
          </Box>
        </Tabs.Content>
        <Tabs.Content value="plan">
          {needsSummary((data) => <PlanTab items={data.treatmentPending} patientId={patientId} />)}
        </Tabs.Content>
        <Tabs.Content value="exams">
          <ExamsTab findings={needsSummary((data) => <OutOfRange findings={data.abnormal} patientId={patientId} />)} patientId={patientId} />
        </Tabs.Content>
        <Tabs.Content value="history">
          <HistoryTab
            summary={summary}
            patientId={patientId}
            reports={reports}
            reportsLoading={reportsLoading}
            onOpenReport={onOpenReport}
          />
        </Tabs.Content>
      </Box>
    </Tabs.Root>
  );
}

function TabCount({ value, label }: { value: number; label: string }) {
  if (value === 0) return null;
  return (
    <>
      <Badge variant="outline" size="1" color="gray" radius="full" ml="1" aria-hidden="true">{value}</Badge>
      <VisuallyHidden>{`, ${value} ${label}`}</VisuallyHidden>
    </>
  );
}

/* ───────────────────────── Resumen ───────────────────────── */

interface SummaryTabProps {
  summary: PatientSummary;
  overview: PatientOverview | undefined;
  overviewPending: boolean;
  patientId: number;
  onTab: (tab: PatientTab) => void;
  assistant?: ReactNode;
}

function SummaryTab({ summary, overview, overviewPending, patientId, onTab, assistant }: SummaryTabProps) {
  if (summary.reportCount === 0) {
    return (
      <Text size="2" color="gray">
        Este paciente aún no tiene informes guardados. Graba un dictado, valida sus temas y guarda el informe para ver el
        resumen.
      </Text>
    );
  }
  const text = overview?.globalSummary || summary.brief;
  const synthesisPending = summary.synthesisPending || overview?.synthesisPending;
  const priorityFindings = topFindings(summary.abnormal);
  const critical = summary.criticality.level === "critical";

  return (
    <Flex direction="column" gap="4">
      <Flex direction="column" gap="2">
        <Flex align="center" gap="2" wrap="wrap">
          <Badge color={critical ? "red" : "gray"} variant={critical ? "solid" : "soft"}>
            Criticidad: {summary.criticality.label}
          </Badge>
          {summary.status && (
            <Text size="2" color="gray">
              {summary.status}
            </Text>
          )}
        </Flex>
        {summary.criticality.reasons.length > 0 && (
          <Text size="1" color="gray">
            {summary.criticality.reasons.join(" · ")}
          </Text>
        )}
      </Flex>

      {(text || synthesisPending) && (
        <Card variant="surface" size="2" style={{ background: "var(--gray-a2)" }}>
          <Flex direction="column" gap="2">
            <SectionTitle title="Síntesis del caso" />
            {text && <Text as="p" size="3" style={{ lineHeight: 1.55, maxWidth: "72ch" }}>{text}</Text>}
            {synthesisPending && (
              <Flex align="center" gap="2" role="status">
                <Spinner size="1" />
                <Text size="1" color="gray">Actualizando la síntesis con lo último consolidado…</Text>
              </Flex>
            )}
          </Flex>
        </Card>
      )}

      <SafetyPoints points={summary.keyPoints} />

      <Flex>
        <Button size="1" color="gray" variant="outline" onClick={() => onTab("plan")}>Ver plan e indicaciones</Button>
      </Flex>

      <Glance
        title="Hallazgos prioritarios"
        total={summary.abnormal.length}
        empty="Sin exámenes ni escalas fuera de rango."
        action={summary.abnormal.length > 0 ? { label: "Ver exámenes", onClick: () => onTab("exams") } : undefined}
      >
        {priorityFindings.map((finding) => (
          <Flex key={`${finding.kind}-${finding.name}`} justify="between" gap="3">
            <Text size="2" truncate>{finding.name}</Text>
            <Text size="2" weight="medium" color={SEVERITY_TEXT[finding.severity]} style={{ whiteSpace: "nowrap" }}>
              {finding.value}
              {finding.unit && ` ${finding.unit}`}
            </Text>
          </Flex>
        ))}
      </Glance>

      <Flex direction="column" gap="2">
        <SectionTitle title="Por área clínica" />
        {overviewPending ? (
          <Skeleton height="120px" />
        ) : !overview ? (
          <Text size="2" color="gray">
            No se pudo cargar la información por áreas.
          </Text>
        ) : (
          <ClinicalAccordion areas={overview.areas.filter((area) => area.area !== PLAN_AREA)} highlights={summary.highlights} patientId={patientId} />
        )}
      </Flex>

      {assistant}

      <Text size="1" color="gray">
        Versión oficial n.º {summary.version} · el resumen sale de lo ya consolidado entre los profesionales
        {overview && overview.contributors.length > 0 && (
          <>
            {" "}
            · Aportaron:{" "}
            {overview.contributors.map((contributor, index) => (
              <span key={contributor.profession}>
                {index > 0 && ", "}
                {professionLabel(contributor.profession)}
                {contributor.inConflict && (
                  <Text color="amber" weight="medium">
                    {" "}
                    (en conflicto)
                  </Text>
                )}
              </span>
            ))}
          </>
        )}
      </Text>
    </Flex>
  );
}

/** Lo que hay que saber antes de actuar: LET, no RCP y alergias, siempre a la vista. */
function SafetyPoints({ points }: { points: KeyPoint[] }) {
  if (points.length === 0) return null;
  return (
    <Flex direction="column" gap="1" aria-label="Alergias y limitaciones terapéuticas">
      <Text size="1" weight="medium" color="gray">
        Alergias y limitaciones terapéuticas
      </Text>
      <Flex gap="x-3" wrap="wrap" style={{ rowGap: 4 }}>
        {points.map((point) => {
          const alert = point.tone === "red" || point.tone === "orange";
          return (
            <Text key={`${point.kind}-${point.label}`} size="2">
              <Text weight="bold" color={alert ? "red" : undefined}>
                {point.label}
              </Text>
              {point.detail && <Text color="gray"> · {point.detail}</Text>}
            </Text>
          );
        })}
      </Flex>
    </Flex>
  );
}

interface GlanceProps {
  title: string;
  total: number;
  empty: string;
  action?: { label: string; onClick: () => void };
  children: ReactNode;
}

/** Un vistazo: lo primero de una lista larga con un enlace a la pestaña que la tiene completa. */
function Glance({ title, total, empty, action, children }: GlanceProps) {
  return (
    <Flex direction="column" gap="2" p="3" style={{ border: "1px solid var(--gray-a5)", borderRadius: "var(--radius-3)" }}>
      <SectionTitle title={title} count={total} />
      {total === 0 ? (
        <Text size="2" color="gray">
          {empty}
        </Text>
      ) : (
        children
      )}
      {action && (
        <Flex mt="1">
          <Button size="1" variant="ghost" onClick={action.onClick}>
            {action.label} →
          </Button>
        </Flex>
      )}
    </Flex>
  );
}

const SEVERITY_RANK: Record<AbnormalSeverity, number> = { critical: 0, high: 1, moderate: 2 };
/** Rojo solo para lo crítico; el resto en tonos neutros/ámbar. */
const SEVERITY_TEXT: Record<AbnormalSeverity, "red" | "amber" | undefined> = {
  critical: "red",
  high: "amber",
  moderate: undefined,
};

/** Los hallazgos de mayor severidad (ya vienen ordenados, pero se asegura). */
function topFindings(findings: AbnormalFinding[]): AbnormalFinding[] {
  return [...findings]
    .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || Number(b.mortality) - Number(a.mortality))
    .slice(0, GLANCE_LIMIT);
}

type LinkedConflict = Pick<Conflict, "id" | "label" | "section"> & { reconciliationId: string };

interface AccordionItem {
  key: string;
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
  muted?: boolean;
  content: ReactNode;
}

/** Áreas clínicas y detalle registrado en una lista: una abierta a la vez. */
function ClinicalAccordion({ areas, highlights, patientId }: { areas: AreaSummary[]; highlights: Highlight[]; patientId: number }) {
  const conflicts = usePatientConflicts(patientId);
  const sections = new Set(areas.flatMap((area) => area.sections));
  const items: AccordionItem[] = [
    ...areas.flatMap((area): AccordionItem[] => {
      const matches = conflicts.filter((conflict) => area.sections.includes(conflict.section));
      const entries = highlights.filter((item) => area.sections.includes(item.section));
      if (!area.informed && matches.length === 0 && entries.length === 0) return [];
      return [{
        key: `area-${area.area}`,
        title: area.area,
        muted: !area.informed,
        hint: matches.length > 1 ? <Badge color="amber" variant="soft">{matches.length} conflictos</Badge> : undefined,
        action: matches.length === 1 ? (
          <ConflictLink conflict={matches[0]} compact />
        ) : undefined,
        content: (
          <Flex direction="column" gap="2">
            <AreaDetail area={area} />
            {matches.length > 1 && matches.map((conflict) => <ConflictLink key={conflict.id} conflict={conflict} />)}
            {entries.map((item, index) => (
              <HighlightRow key={`${item.reportId}-${item.section}-${index}`} item={item} patientId={patientId} />
            ))}
          </Flex>
        ),
      }];
    }),
    ...groupHighlights(highlights.filter((item) => !sections.has(item.section))).map(
      ([group, entries]): AccordionItem => ({
        key: `group-${group}`,
        title: group,
        hint: (
          <Text size="1" color="gray">
            {entries.length}
          </Text>
        ),
        content: (
          <Flex direction="column" gap="2">
            {entries.map((item, index) => (
              <HighlightRow key={`${item.reportId}-${item.section}-${index}`} item={item} patientId={patientId} />
            ))}
          </Flex>
        ),
      }),
    ),
  ];
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <Text size="2" color="gray">
        Todavía no hay información para organizar por áreas.
      </Text>
    );
  }
  return (
    <Box style={{ border: "1px solid var(--gray-a5)", borderRadius: "var(--radius-3)", overflow: "hidden" }}>
      {items.map((item, index) => {
        const open = openKey === item.key;
        const panelId = `accordion-${patientId}-${index}`;
        return (
          <Box key={item.key} style={index > 0 ? { borderTop: "1px solid var(--gray-a4)" } : undefined}>
            <Flex align="center" gap="2" pr={item.action ? "3" : undefined}>
              <Button
                type="button"
                variant="ghost"
                color="gray"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setOpenKey(open ? null : item.key)}
                style={{
                  flex: 1,
                  minWidth: 0,
                  height: "auto",
                  margin: 0,
                  padding: "10px 12px",
                  justifyContent: "space-between",
                  borderRadius: 0,
                  color: item.muted ? "var(--gray-10)" : "var(--gray-12)",
                }}
              >
                <Flex align="center" gap="2" style={{ minWidth: 0 }}>
                  <Text aria-hidden="true" color="gray" style={{ width: 12 }}>
                    {open ? "▾" : "▸"}
                  </Text>
                  <Text size="2" weight="medium" style={{ whiteSpace: "normal", textAlign: "left" }}>
                    {item.title}
                  </Text>
                </Flex>
                {item.hint}
              </Button>
              {item.action}
            </Flex>
            <Box id={panelId} hidden={!open} px="3" pb="3" pl="6">
              {open && item.content}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

function usePatientConflicts(patientId: number): LinkedConflict[] {
  const { data: reconciliations = [] } = useReconciliations();
  return reconciliations
    .filter((item) => item.patientId === patientId)
    .flatMap((item) =>
      item.conflicts
        .filter((conflict) => conflict.status === "open")
        .map(({ id, label, section }) => ({ id, label, section, reconciliationId: item.id })),
    );
}

function ConflictLink({ conflict, compact = false }: { conflict: LinkedConflict; compact?: boolean }) {
  return (
    <ThemeLink size="1" color="amber" weight="medium" asChild>
      <Link
        to="/reconciliation"
        search={{ id: conflict.reconciliationId, conflict: conflict.id }}
        aria-label={compact ? `Ver conflicto: ${conflict.label}` : undefined}
        style={compact ? { whiteSpace: "nowrap" } : undefined}
      >
        {compact ? "Ver conflicto" : `Ver conflicto · ${conflict.label}`}
      </Link>
    </ThemeLink>
  );
}

function AreaDetail({ area }: { area: AreaSummary }) {
  return (
    <Flex direction="column" gap="2">
      <Text size="2" color={area.informed ? undefined : "gray"} style={{ lineHeight: 1.5 }}>
        {area.informed
          ? area.summary || "Hay datos registrados, pero aún sin síntesis."
          : "Aún no se ha registrado nada en esta área."}
      </Text>
      {area.contributors.length > 0 && (
        <Text size="1" color="gray">
          Aportó: {area.contributors.map((profession) => professionLabel(profession)).join(", ")}
        </Text>
      )}
    </Flex>
  );
}

/* ───────────────────────── Plan ───────────────────────── */

function PlanTab({ items, patientId }: { items: Highlight[]; patientId: number }) {
  const conflicts = usePatientConflicts(patientId);

  return (
    <Flex direction="column" gap="4">
      {CARE_SECTIONS.map(({ id, title, horizon, empty, groups }) => {
        const headingId = `${id}-${patientId}`;
        const filled = groups
          .map((group) => ({
            ...group,
            entries: items.filter((item) => group.sections.includes(item.section)),
            conflicts: conflicts.filter((conflict) => group.sections.includes(conflict.section)),
          }))
          .filter((group) => group.entries.length > 0 || group.conflicts.length > 0);

        return (
          <Card key={id} variant="surface" size="2" asChild>
            <section aria-labelledby={headingId}>
              <Flex direction="column" gap="4">
                <Flex align="baseline" gap="2" wrap="wrap">
                  <Heading as="h2" size="4" id={headingId}>{title}</Heading>
                  <Text size="2" color="gray">{horizon}</Text>
                </Flex>
                {filled.length === 0 && <Text size="2" color="gray">{empty}</Text>}
                {filled.map((group) => (
                  <Flex key={group.title} direction="column" gap="2">
                    <Heading as="h3" size="2">{group.title}</Heading>
                    {group.conflicts.map((conflict) => <ConflictLink key={conflict.id} conflict={conflict} />)}
                    {group.entries.map((item, index) => (
                      <HighlightRow key={`${item.reportId}-${item.section}-${index}`} item={item} patientId={patientId} />
                    ))}
                  </Flex>
                ))}
              </Flex>
            </section>
          </Card>
        );
      })}
    </Flex>
  );
}

/* ───────────────────────── Exámenes ───────────────────────── */

function ExamsTab({ findings, patientId }: { findings: ReactNode; patientId: number }) {
  const { data: trends, isPending: trendsPending } = usePatientTrends(patientId);
  return (
    <Flex direction="column" gap="5">
      {findings}

      <Flex direction="column" gap="2">
        <SectionTitle title="Tendencias" count={trends?.length} detail="Evolución de exámenes y escalas" />
        {trendsPending ? (
          <Skeleton height="80px" />
        ) : !trends ? (
          <Text size="2" color="gray">No se pudieron cargar las tendencias.</Text>
        ) : trends.length === 0 ? (
          <Text size="2" color="gray">
            Aún no hay dos o más mediciones de un mismo examen o escala para mostrar su evolución.
          </Text>
        ) : (
          <TrendList trends={trends} />
        )}
      </Flex>

      <Flex direction="column" gap="2">
        <SectionTitle title="Evidencia cargada" />
        <EvidencePanel patientId={patientId} />
      </Flex>
    </Flex>
  );
}

function OutOfRange({ findings, patientId }: { findings: AbnormalFinding[]; patientId: number }) {
  const { data: evidence } = useEvidence(patientId);
  const evidenceIds = new Set(evidence?.map((item) => item.id));
  return (
    <Flex direction="column" gap="2">
      <SectionTitle
        title="Fuera de rango"
        count={findings.length}
        detail="Laboratorio y escalas · lo más grave y ligado a mortalidad primero"
      />
      {findings.length === 0 ? (
        <Text size="2" color="gray">Sin exámenes ni escalas fuera de rango.</Text>
      ) : (
        <Flex direction="column">
          {findings.map((finding, index) => (
            <AbnormalRow
              key={`${finding.kind}-${finding.name}`}
              finding={finding}
              first={index === 0}
              patientId={patientId}
              evidenceAvailable={finding.evidenceId != null && evidenceIds.has(finding.evidenceId)}
            />
          ))}
        </Flex>
      )}
    </Flex>
  );
}

function AbnormalRow({ finding, first, patientId, evidenceAvailable }: {
  finding: AbnormalFinding;
  first: boolean;
  patientId: number;
  evidenceAvailable: boolean;
}) {
  const color = SEVERITY_TEXT[finding.severity];
  return (
    <Flex
      align="center"
      justify="between"
      gap="3"
      wrap="wrap"
      py="2"
      style={first ? undefined : { borderTop: "1px solid var(--gray-a4)" }}
    >
      <Flex direction="column" style={{ minWidth: 0 }}>
        <Text size="2" weight="medium">
          {finding.name}
        </Text>
        <Text size="1" color="gray">
          <Text color={color} weight={color ? "medium" : undefined}>
            {finding.severityLabel}
          </Text>
          {finding.mortality && " · ligado a mortalidad"} · {finding.kind === "scale" ? "Escala" : "Laboratorio"}
          {finding.note && ` · ${finding.note}`}
          {finding.reference && ` · referencia ${finding.reference}`}
          {finding.at && ` · ${DATE_FORMAT.format(new Date(finding.at))}`}
        </Text>
      </Flex>
      <Flex align="center" gap="3" ml="auto" wrap="wrap">
        <Text size="3" weight="bold" color={color} style={{ whiteSpace: "nowrap" }}>
          {finding.value}
          {finding.unit && (
            <Text size="1" color="gray" weight="regular"> {finding.unit}</Text>
          )}
        </Text>
        {evidenceAvailable && (
          <Button
            size="1"
            variant="outline"
            color="gray"
            aria-label={`Ver examen: ${finding.name}`}
            onClick={() => {
              const record = document.getElementById(`evidence-${finding.evidenceId}`);
              record?.scrollIntoView({ block: "center" });
              record?.focus({ preventScroll: true });
            }}
          >
            Ver examen
          </Button>
        )}
        {finding.reportId && (
          <Button size="1" variant="outline" color="gray" asChild>
            <Link to="/" search={{ patient: String(patientId), report: finding.reportId, section: "escalas" }} aria-label={`Ver informe: ${finding.name}`}>
              Ver informe
            </Link>
          </Button>
        )}
      </Flex>
    </Flex>
  );
}

/* ───────────────────────── Historial ───────────────────────── */

interface HistoryTabProps {
  summary: PatientSummary | undefined;
  patientId: number;
  reports: Report[];
  reportsLoading: boolean;
  onOpenReport: (reportId: string) => void;
}

function HistoryTab({ summary, patientId, reports, reportsLoading, onOpenReport }: HistoryTabProps) {
  return (
    <Flex direction="column" gap="5">
      <Flex direction="column" gap="2">
        <SectionTitle title="Informes" count={reports.length} />
        {reportsLoading ? <Skeleton height="80px" /> : <ReportHistory reports={reports} onOpen={onOpenReport} />}
      </Flex>

      {summary && summary.byProfession.length > 0 && (
        <Flex direction="column" gap="2">
          <SectionTitle title="Por profesional" />
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
                <ThemeLink size="1" asChild>
                  <Link to="/" search={{ patient: String(patientId), report: activity.lastReportId }}>
                    Abrir el último informe
                  </Link>
                </ThemeLink>
              </Flex>
            ))}
          </Flex>
        </Flex>
      )}

      <VersionHistory patientId={patientId} />
    </Flex>
  );
}

function ReportHistory({ reports, onOpen }: { reports: Report[]; onOpen: (reportId: string) => void }) {
  if (reports.length === 0) {
    return (
      <Text size="2" color="gray">
        Aún no hay informes de este paciente.
      </Text>
    );
  }
  return (
    <Flex direction="column" gap="1">
      {reports.map((report) => (
        <Button
          key={report.id}
          variant="ghost"
          color="gray"
          onClick={() => onOpen(report.id)}
          style={{ justifyContent: "space-between", height: "auto", padding: "8px", margin: 0, color: "var(--gray-12)" }}
        >
          <Flex direction="column" align="start" style={{ textAlign: "left" }}>
            <Text size="2">{reportTitle(report.sequence, report.profession)}</Text>
            <Text size="1" color="gray">
              {report.authorName} · {DATE_FORMAT.format(new Date(report.recordedAt))}
            </Text>
          </Flex>
        </Button>
      ))}
    </Flex>
  );
}

const REASON_LABEL = {
  official: "Primer informe guardado",
  merge: "Informe sin conflictos incorporado",
  reconciliation: "Conflictos resueltos entre profesionales",
} as const;

/** Todas las versiones oficiales del paciente: la vigente y las anteriores, con el informe que las originó. */
export function VersionHistory({ patientId }: { patientId: number }) {
  const { data: versions = [], isPending } = usePatientVersions(patientId);
  return (
    <Flex direction="column" gap="2">
      <SectionTitle title="Versiones oficiales" count={versions.length} />
      {isPending ? (
        <Skeleton height="60px" />
      ) : versions.length === 0 ? (
        <Text size="2" color="gray">
          Aún no hay una versión oficial.
        </Text>
      ) : (
        <Flex direction="column" gap="2">
          {versions.map((version) => (
            <Flex key={version.version} justify="between" align="center" gap="3" wrap="wrap">
              <Flex direction="column">
                <Text size="2">
                  <Text weight="medium">Versión {version.version}</Text>
                  {version.isCurrent && <Text color="teal"> · vigente</Text>} · {REASON_LABEL[version.reason]}
                </Text>
                <Text size="1" color="gray">
                  {version.sourceProfession && `${professionLabel(version.sourceProfession)} · `}
                  {version.sourceAuthor && `${version.sourceAuthor} · `}
                  {DATE_FORMAT.format(new Date(version.created_at))}
                </Text>
              </Flex>
              {version.sourceReportId && (
                <ThemeLink size="1" asChild>
                  <Link to="/" search={{ patient: String(patientId), report: version.sourceReportId }}>
                    Ver informe de origen
                  </Link>
                </ThemeLink>
              )}
              <VersionChanges changes={version.changes} />
            </Flex>
          ))}
        </Flex>
      )}
    </Flex>
  );
}

/* ───────────────────────── Compartido ───────────────────────── */

interface SectionTitleProps {
  title: string;
  count?: number;
  detail?: string;
  tone?: "amber";
}

/** Encabezado sobrio de un bloque: título, cuántos hay y una nota opcional. */
function SectionTitle({ title, count, detail, tone }: SectionTitleProps) {
  return (
    <Flex align="baseline" gap="2" wrap="wrap">
      <Text size="2" weight="bold" color={tone}>
        {title}
      </Text>
      {count !== undefined && count > 0 && (
        <Text size="1" color="gray">
          {count}
        </Text>
      )}
      {detail && (
        <Text size="1" color="gray">
          · {detail}
        </Text>
      )}
    </Flex>
  );
}

function HighlightRow({ item, patientId }: { item: Highlight; patientId: number }) {
  return (
    <Flex justify="between" align="baseline" gap="3" wrap="wrap">
      <Text size="2" style={{ minWidth: 0, flex: "1 1 240px" }}>
        {item.severity && (
          <Text color={item.severity === "alta" ? "red" : "gray"} weight="medium">
            {item.severity} ·{" "}
          </Text>
        )}
        {item.text}
      </Text>
      <ThemeLink size="1" color="gray" asChild>
        <Link
          to="/"
          search={{ patient: String(patientId), report: item.reportId, section: item.section }}
          title={`Informe de ${item.authorName}`}
          style={{ whiteSpace: "nowrap" }}
        >
          {professionLabel(item.profession)} · {sectionLabel(item.section)}
        </Link>
      </ThemeLink>
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
