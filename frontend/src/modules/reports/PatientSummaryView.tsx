import { Badge, Button, Callout, Card, Flex, Heading, Skeleton, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import {
  usePatientSummary,
  usePatientVersions,
  type CriticalityLevel,
  type Highlight,
  type PatientSummary,
} from "../patients/api";
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
  onOpenReports: () => void;
}

/** Estado del paciente arriba (criticidad, resumen, pendientes del tratamiento); el resto, plegado. */
export function PatientSummaryView({ patientId, onOpenReports }: PatientSummaryViewProps) {
  const { data: summary, isPending, isError, error } = usePatientSummary(patientId);

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

  const groups = groupHighlights(summary.highlights);
  return (
    <Flex direction="column" gap="3">
      <Text size="1" color="gray">
        Versión oficial n.º {summary.version} · el resumen sale de lo ya consolidado entre los profesionales.
      </Text>
      <StatusCard summary={summary} patientId={patientId} />

      <Flex justify="between" align="center" gap="3" wrap="wrap" mt="2">
        <Heading size="3">Más información</Heading>
        <Button variant="soft" onClick={onOpenReports}>
          Ver los informes del paciente
        </Button>
      </Flex>

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

function StatusCard({ summary, patientId }: { summary: PatientSummary; patientId: number }) {
  const { criticality } = summary;
  return (
    <Card variant="classic" style={{ borderLeft: `4px solid var(--${CRITICALITY_COLOR[criticality.level]}-9)` }}>
      <Flex direction="column" gap="3">
        <Flex align="center" gap="3" wrap="wrap">
          <Badge size="3" color={CRITICALITY_COLOR[criticality.level]} variant="solid">
            Criticidad: {criticality.label}
          </Badge>
          {summary.status && <Text size="2">{summary.status}</Text>}
        </Flex>

        {criticality.reasons.length > 0 && (
          <Flex gap="2" wrap="wrap">
            {criticality.reasons.map((reason) => (
              <Badge key={reason} color="gray" variant="surface">
                {reason}
              </Badge>
            ))}
          </Flex>
        )}

        {summary.brief && <Text size="3">{summary.brief}</Text>}

        <Flex direction="column" gap="2">
          <Text size="2" weight="medium">
            Pendientes del tratamiento
          </Text>
          {summary.treatmentPending.length === 0 ? (
            <Text size="2" color="gray">
              Sin pendientes registrados.
            </Text>
          ) : (
            summary.treatmentPending.map((item, index) => (
              <HighlightRow key={`${item.reportId}-${item.section}-${index}`} item={item} patientId={patientId} showGroup />
            ))
          )}
        </Flex>
      </Flex>
    </Card>
  );
}

function HighlightRow({ item, patientId, showGroup = false }: { item: Highlight; patientId: number; showGroup?: boolean }) {
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
        <Text size="2">{item.text}</Text>
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
function VersionHistory({ patientId }: { patientId: number }) {
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
