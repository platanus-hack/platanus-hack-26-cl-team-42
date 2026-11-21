import type { ReactNode } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Skeleton, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "../../components/EmptyState";
import { CRITICALITY_META } from "../inbox/inbox";
import {
  usePatientOverview,
  usePatientSummary,
  type AreaSummary,
  type Contributor,
  type PatientWithCount,
} from "../patients/api";
import { useReconciliations, type Conflict, type ConflictSide } from "../reconciliation/api";
import { professionLabel } from "../recordings/professions";
import { VersionHistory } from "./PatientSummaryView";
import { StatusBadge } from "./ReportView";
import type { Report } from "./api";
import { anonymizeNames, reportTitle } from "./format";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

interface PatientReportsViewProps {
  patient: PatientWithCount;
  /** Informes guardados del paciente, de cualquier profesional. */
  reports: Report[];
  onOpenReport: (reportId: string) => void;
  onBack: () => void;
}

/**
 * Todo lo que se sabe del paciente: resumen global, información por áreas, conflictos entre
 * informes e informes anteriores. A los profesionales se les identifica por su rol, no por su nombre.
 */
export function PatientReportsView({ patient, reports, onOpenReport, onBack }: PatientReportsViewProps) {
  const { data: reconciliations = [] } = useReconciliations();
  const conflicts = reconciliations
    .filter((item) => item.patientId === patient.id)
    .flatMap((item) => item.conflicts)
    .filter((conflict) => conflict.status === "open");

  return (
    <Flex direction="column" gap="5">
      <Flex direction="column" gap="2" align="start">
        <Button variant="ghost" color="gray" onClick={onBack}>
          ← Volver a {patient.name}
        </Button>
        <Heading size="5">Vista resumen · {patient.name}</Heading>
        <Text size="2" color="gray">
          {[patient.bed, patient.identifier].filter(Boolean).join(" · ")}
        </Text>
      </Flex>

      <GlobalSummary patient={patient} conflictCount={conflicts.length} />
      <AreasSection patientId={patient.id} conflicts={conflicts} />
      <OpenConflicts conflicts={conflicts} />
      <PreviousReports patientId={patient.id} reports={reports} onOpenReport={onOpenReport} />
    </Flex>
  );
}

function GlobalSummary({ patient, conflictCount }: { patient: PatientWithCount; conflictCount: number }) {
  const { data: summary } = usePatientSummary(patient.id);
  const { data: overview, isPending, isError, error } = usePatientOverview(patient.id);
  const criticality = summary?.criticality;
  const color = CRITICALITY_META[patient.criticality].color;

  return (
    <Section title="Resumen global">
      <Card variant="classic" style={{ borderLeft: `4px solid var(--${color}-9)` }}>
        <Flex direction="column" gap="3">
          <Flex align="center" gap="3" wrap="wrap">
            {criticality && (
              <Badge size="3" color={color} variant="solid">
                Criticidad: {criticality.label}
              </Badge>
            )}
            {summary?.status && <Text size="2">{summary.status}</Text>}
          </Flex>

          {isError ? (
            <Callout.Root color="red">
              <Callout.Text>No se pudo cargar el resumen: {error.message}</Callout.Text>
            </Callout.Root>
          ) : isPending ? (
            <Skeleton height="96px" />
          ) : overview.globalSummary ? (
            <Text size="3" style={{ lineHeight: 1.6 }}>
              {overview.globalSummary}
            </Text>
          ) : (
            <Text size="2" color="gray">
              Este paciente aún no tiene informes consolidados para resumir.
            </Text>
          )}

          {criticality && criticality.reasons.length > 0 && (
            <Flex gap="2" wrap="wrap">
              {criticality.reasons.map((reason) => (
                <Badge key={reason} color="gray" variant="surface">
                  {reason}
                </Badge>
              ))}
            </Flex>
          )}

          {overview && overview.contributors.length > 0 && <Contributors contributors={overview.contributors} />}

          {overview && overview.version > 0 && (
            <Text size="1" color="gray">
              Versión oficial n.º {overview.version}, consolidada entre los profesionales.
              {conflictCount > 0 &&
                ` Refleja lo ya acordado: ${conflictCount === 1 ? "el conflicto abierto" : `los ${conflictCount} conflictos abiertos`} más abajo aún no se incorpora${conflictCount === 1 ? "" : "n"}.`}
            </Text>
          )}
        </Flex>
      </Card>
    </Section>
  );
}

/** Las profesiones que aportaron informes; las que esperan reconciliarse se marcan aparte. */
function Contributors({ contributors }: { contributors: Contributor[] }) {
  return (
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
  );
}

function AreasSection({ patientId, conflicts }: { patientId: number; conflicts: Conflict[] }) {
  const { data: overview, isPending } = usePatientOverview(patientId);

  return (
    <Section title="Información por áreas" detail="Síntesis de lo consolidado, por área clínica.">
      {isPending ? (
        <Skeleton height="160px" />
      ) : !overview || overview.areas.length === 0 ? (
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
    </Section>
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

function OpenConflicts({ conflicts }: { conflicts: Conflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <Section
      title="Conflictos entre informes"
      detail="Lo que dijeron distintas profesiones sobre un mismo dato; lo resuelven quienes lo reportaron."
    >
      <Flex direction="column" gap="3">
        {conflicts.map((conflict) => (
          <Card key={conflict.id} variant="surface" style={{ borderLeft: "4px solid var(--orange-9)" }}>
            <Flex direction="column" gap="3">
              <Flex justify="between" align="start" gap="3" wrap="wrap">
                <Flex direction="column" style={{ minWidth: 0, flex: 1 }}>
                  <Text weight="medium">{conflict.label}</Text>
                  {conflict.explanation && (
                    <Text size="2" color="gray">
                      {anonymizeNames(
                        conflict.explanation,
                        [conflict.sideA, conflict.sideB].map((side) => ({ name: side.authorName, profession: side.profession })),
                      )}
                    </Text>
                  )}
                </Flex>
                <Link to="/reconciliation" search={{ id: conflict.reconciliationId }}>
                  <Button size="1" color="orange" variant="soft">
                    {conflict.canAccept || conflict.canAgree || conflict.canDecide ? "Resolver" : "Ver"}
                  </Button>
                </Link>
              </Flex>
              <Grid columns={{ initial: "1", sm: "2" }} gap="3">
                <ConflictSideCard side={conflict.sideA} />
                <ConflictSideCard side={conflict.sideB} />
              </Grid>
            </Flex>
          </Card>
        ))}
      </Flex>
    </Section>
  );
}

function ConflictSideCard({ side }: { side: ConflictSide }) {
  return (
    <Card variant="classic">
      <Flex direction="column" gap="1">
        <Text size="1" color="gray">
          {professionLabel(side.profession)}
        </Text>
        <Text size="2" weight="medium">
          {side.value}
        </Text>
        {side.evidence && (
          <Text size="1" color="gray" style={{ fontStyle: "italic" }}>
            «{side.evidence}»
          </Text>
        )}
      </Flex>
    </Card>
  );
}

interface PreviousReportsProps {
  patientId: number;
  reports: Report[];
  onOpenReport: (reportId: string) => void;
}

function PreviousReports({ patientId, reports, onOpenReport }: PreviousReportsProps) {
  return (
    <Section title="Informes anteriores" detail={`${reports.length} ${reports.length === 1 ? "informe" : "informes"}`}>
      {reports.length === 0 ? (
        <EmptyState title="Aún no hay informes" description="Los informes guardados de este paciente aparecerán aquí." />
      ) : (
        <Flex direction="column" gap="2">
          {reports.map((report) => (
            <Card key={report.id} asChild variant="surface">
              <button
                type="button"
                onClick={() => onOpenReport(report.id)}
                style={{ textAlign: "left", cursor: "pointer", width: "100%" }}
              >
                <Flex justify="between" align="center" gap="3" wrap="wrap">
                  <Flex direction="column">
                    <Text size="2" weight="medium">
                      {reportTitle(report.sequence, report.profession)}
                    </Text>
                    <Text size="1" color="gray">
                      {DATE_FORMAT.format(new Date(report.recordedAt))}
                    </Text>
                  </Flex>
                  {report.status !== "done" && <StatusBadge report={report} />}
                </Flex>
              </button>
            </Card>
          ))}
        </Flex>
      )}
      <VersionHistory patientId={patientId} />
    </Section>
  );
}

function Section({ title, detail, children }: { title: string; detail?: string; children: ReactNode }) {
  return (
    <Flex direction="column" gap="3">
      <Flex direction="column">
        <Heading size="4">{title}</Heading>
        {detail && (
          <Text size="1" color="gray">
            {detail}
          </Text>
        )}
      </Flex>
      {children}
    </Flex>
  );
}
