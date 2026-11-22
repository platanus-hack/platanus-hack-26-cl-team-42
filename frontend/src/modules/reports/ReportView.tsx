import { useEffect, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Badge, Button, Callout, Card, Flex, Heading, Spinner, Text } from "@radix-ui/themes";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import { professionLabel } from "../recordings/professions";
import { ComplementDialog } from "../templates/ComplementDialog";
import { sectionLabel } from "../templates/recordFields";
import { useTemplate } from "../templates/api";
import { reportTitle, sectionAnchor } from "./format";
import { pendingSections } from "./pending";
import { ReportChangesSection } from "./ReportChanges";
import { ReviewHeaderAction, ReviewPointCallout, ReviewTopicPicker } from "./ReviewPanel";
import { SectionBlock } from "./SectionBlock";
import { useReportReview } from "./useReportReview";
import type { Homologation, Report } from "./api";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short" });

interface ReportViewProps {
  report: Report;
  /** Permite completar la información pendiente (solo en el listado de informes). */
  interactive?: boolean;
  /** Sección a destacar y mostrar (viene de un enlace del asistente o del resumen). */
  focusSection?: string;
}

/**
 * El informe completo: paciente, autor, orden en la categoría, información pendiente y registro.
 * Mientras su autor lo valida, se revisa por excepción: solo los puntos pendientes, con la acción
 * («Validar y continuar» o «Guardar informe») en el encabezado.
 */
export function ReportView(props: ReportViewProps) {
  return <ReportContent key={`${props.report.id}:${props.focusSection ?? ""}`} {...props} />;
}

function ReportContent({ report, interactive = true, focusSection }: ReportViewProps) {
  const { data: template } = useTemplate(report.templateSlug, report.templateVersion);
  const data = report.data ?? {};
  const order = template?.output_schema.required ?? Object.keys(data);
  const pending = pendingSections(data, order);
  const validating = interactive && report.canEdit && report.status === "review";
  const busy = report.status === "processing" || report.extractionStatus === "processing" || report.extractionStatus === "pending";
  const review = useReportReview(report, focusSection);
  const activeTopic = report.topics.find((topic) => topic.id === review.activeTopicId);
  const activeSections = activeTopic?.sections ?? (review.current ? [review.current.section] : []);
  const sectionBusy = busy || review.reviewing;

  useFocusedSection(focusSection, report.id, report.data !== null);

  const renderSections = (keys: string[], canComplete = false) =>
    keys.map((key) => (
      <SectionBlock
        key={key}
        report={report}
        sectionKey={key}
        pendingFields={pending.find((section) => section.key === key)?.fields ?? []}
        focused={focusSection === key}
        canComplete={canComplete}
        schema={template?.output_schema.properties[key]}
        definitions={template?.output_schema.$defs}
        busy={sectionBusy}
      />
    ));

  return (
    <Flex direction="column" gap="4">
      <ReportHeader report={report} action={validating && <ReviewHeaderAction review={review} busy={busy} />} />

      {busy && (
        <Callout.Root color="blue">
          <Flex align="center" gap="2">
            <Spinner size="2" />
            <Callout.Text>
              {report.extractionStatus === "done" || report.status === "processing"
                ? "Homologando los conceptos del informe…"
                : "Incorporando la información nueva: transcribiendo, parseando y homologando…"}
            </Callout.Text>
          </Flex>
        </Callout.Root>
      )}

      {report.status === "failed" && (
        <Callout.Root color="red">
          <Callout.Text>{report.error || "No se pudo generar el informe."}</Callout.Text>
        </Callout.Root>
      )}

      <ConsolidationNotice report={report} />

      <ReportChangesSection report={report} enabled={report.data !== null && !busy && report.status !== "failed"} />

      {!validating && <ConceptSummary homologations={report.homologations} />}

      {!validating && report.data !== null && (
        <PendingInformation report={report} pending={pending} interactive={false} busy={busy} />
      )}

      {validating && report.data !== null && (
        <Card variant="classic">
          <Flex direction="column" gap="3">
            <ReviewTopicPicker topics={report.topics} review={review} />
            {activeTopic && <Heading size="3">{activeTopic.label}</Heading>}
            {review.current && <ReviewPointCallout report={report} item={review.current} busy={sectionBusy} />}
            {renderSections(activeSections, true)}
            {focusSection && !activeSections.includes(focusSection) && report.noteSections.includes(focusSection) &&
              renderSections([focusSection])}
          </Flex>
        </Card>
      )}

      {!validating && report.data !== null && (
        <Flex direction="column" gap="3">
          {report.topics.map((topic) => {
            const pendingCount = pending.filter((section) => topic.sections.includes(section.key)).length;
            return (
              <CollapsibleSection
                key={topic.id}
                title={topic.label}
                detail={`${topic.sections.length} ${topic.sections.length === 1 ? "sección" : "secciones"}`}
                badge={pendingCount > 0 ? { label: `${pendingCount} sin completar`, color: "gray" } : undefined}
                open={focusSection !== undefined && topic.sections.includes(focusSection)}
              >
                <Flex direction="column" gap="3">
                  {renderSections(topic.sections)}
                </Flex>
              </CollapsibleSection>
            );
          })}
          {/* Familia y observaciones: notas del informe, sin categoría ni revisión. */}
          {report.noteSections.map((key) => (
            <SectionBlock
              key={key}
              report={report}
              sectionKey={key}
              pendingFields={[]}
              focused={focusSection === key}
            />
          ))}
        </Flex>
      )}
    </Flex>
  );
}

/** Desplaza la vista hasta la sección referenciada cuando el informe ya tiene contenido. */
function useFocusedSection(section: string | undefined, reportId: string, ready: boolean) {
  useEffect(() => {
    if (!section || !ready) return;
    const timer = setTimeout(() => {
      document.getElementById(sectionAnchor(section))?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
    return () => clearTimeout(timer);
  }, [section, reportId, ready]);
}

function ReportHeader({ report, action }: { report: Report; action?: ReactNode }) {
  return (
    <Flex direction="column" gap="2">
      <Flex justify="between" align="start" gap="3" wrap="wrap">
        <Flex align="center" gap="2" wrap="wrap">
          <Heading size="4">{reportTitle(report.sequence, report.profession)}</Heading>
          <Badge color="gray" variant="soft">
            N.º {report.sequence} · {professionLabel(report.profession)}
          </Badge>
          <StatusBadge report={report} />
        </Flex>
        {action}
      </Flex>
      <PatientLine report={report} />
      <Text size="2" color="gray">
        {report.templateName}
      </Text>
      <Text size="2" color="gray">
        Generado por <strong>{report.authorName}</strong> · dictado del {DATE_FORMAT.format(new Date(report.recordedAt))} ·
        informe creado el {DATE_FORMAT.format(new Date(report.created_at))}
      </Text>
    </Flex>
  );
}

export function StatusBadge({ report }: { report: Report }) {
  if (report.status === "done") {
    return (
      <Badge color="green" variant="soft">
        Guardado
      </Badge>
    );
  }
  if (report.status === "review") {
    return (
      <Badge color="amber" variant="soft">
        Por validar
      </Badge>
    );
  }
  if (report.status === "failed") {
    return (
      <Badge color="red" variant="soft">
        Error
      </Badge>
    );
  }
  return (
    <Badge color="blue" variant="soft">
      Generando
    </Badge>
  );
}

const CONSOLIDATION_NOTICE = {
  official: ["green", "Es el primer informe guardado del paciente: pasó a ser su versión oficial."],
  merged: ["green", "Coincide con la versión oficial: se incorporó sin conflictos y nació una versión nueva."],
  consolidated: ["green", "Sus conflictos se resolvieron entre los profesionales y quedó incorporado a la versión oficial."],
} as const;

/** Qué pasó con el informe al guardarse respecto de la versión oficial del paciente. */
function ConsolidationNotice({ report }: { report: Report }) {
  if (report.status !== "done") return null;
  if (report.consolidation === "reconciling") {
    return (
      <Callout.Root color="orange">
        <Flex direction="column" gap="2">
          <Callout.Text>
            Este informe choca con lo ya reportado por otro profesional. Se avisó a los implicados y está en reconciliación:
            la versión oficial no cambia hasta resolver los conflictos.
          </Callout.Text>
          <Flex>
            <Link to="/reconciliation" search={{}}>
              <Button size="1" color="orange" variant="soft">
                Ir a resolver los conflictos
              </Button>
            </Link>
          </Flex>
        </Flex>
      </Callout.Root>
    );
  }
  const notice = report.consolidation === "pending" ? undefined : CONSOLIDATION_NOTICE[report.consolidation];
  return notice ? (
    <Callout.Root color={notice[0]} size="1">
      <Callout.Text>{notice[1]}</Callout.Text>
    </Callout.Root>
  ) : null;
}

function PatientLine({ report }: { report: Report }) {
  const patient = report.patient;
  if (!patient) {
    return (
      <Text size="2" color="gray">
        Paciente: {report.patientReference || "sin paciente"}
      </Text>
    );
  }
  return (
    <Text size="2">
      Paciente: <strong>{patient.name}</strong>
      {patient.identifier && ` · ${patient.identifier}`}
      {patient.bed && ` · ${patient.bed}`}
    </Text>
  );
}

interface PendingInformationProps {
  report: Report;
  pending: ReturnType<typeof pendingSections>;
  interactive: boolean;
  busy: boolean;
}

const VISIBLE_FIELDS = 4;

/** Qué quedó sin información y la opción de completarlo con texto o con otro audio (en este mismo informe). */
function PendingInformation({ report, pending, interactive, busy }: PendingInformationProps) {
  const [expanded, setExpanded] = useState(false);
  if (pending.length === 0) {
    return (
      <Callout.Root color="green" size="1">
        <Callout.Text>El informe no tiene información pendiente.</Callout.Text>
      </Callout.Root>
    );
  }
  const shown = expanded ? pending : pending.slice(0, 5);
  const canComplete = interactive && report.canEdit;

  return (
    <Card variant="classic">
      <Flex direction="column" gap="3">
        <Flex justify="between" align="center" gap="2" wrap="wrap">
          <Flex direction="column">
            <Text weight="medium">Información pendiente</Text>
            <Text size="2" color="gray">
              {pending.length} {pending.length === 1 ? "sección" : "secciones"} con datos sin informar.
              {interactive &&
                (report.canEdit
                  ? " Complétalas con texto o con un audio: se transcribe, parsea y homologa dentro de este informe."
                  : ` Solo ${report.authorName} puede completar este informe; un audio nuevo genera un informe nuevo.`)}
            </Text>
          </Flex>
        </Flex>

        {shown.map((section) => (
          <Flex key={section.key} justify="between" align="center" gap="3" wrap="wrap">
            <Flex direction="column" style={{ minWidth: 0, flex: 1 }}>
              <Text size="2" weight="medium">
                {sectionLabel(section.key)}
              </Text>
              <Text size="1" color="gray">
                {section.fields.slice(0, VISIBLE_FIELDS).join(", ")}
                {section.fields.length > VISIBLE_FIELDS && ` y ${section.fields.length - VISIBLE_FIELDS} más`}
              </Text>
            </Flex>
            {canComplete && (
              <ComplementDialog
                extractionId={report.extractionId}
                section={section.key}
                label={sectionLabel(section.key)}
                disabled={busy}
              />
            )}
          </Flex>
        ))}

        {pending.length > shown.length || expanded ? (
          <Flex>
            <Button size="1" variant="ghost" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "Ver menos" : `Ver las ${pending.length} secciones`}
            </Button>
          </Flex>
        ) : null}
      </Flex>
    </Card>
  );
}

/** Los términos que se reemplazaron por su representante común. */
export function ConceptSummary({ homologations }: { homologations: Homologation[] }) {
  const changed = homologations.filter((item) => item.changed);
  if (homologations.length === 0) return null;
  return (
    <Card variant="classic">
      <Flex direction="column" gap="2">
        <Text weight="medium">Conceptos homologados</Text>
        <Text size="2" color="gray">
          {changed.length} {changed.length === 1 ? "término unificado" : "términos unificados"} · {homologations.length - changed.length}{" "}
          ya usaban el concepto común
        </Text>
        <Flex gap="2" wrap="wrap">
          {changed.map((item, index) => (
            <HomologationChip key={`${item.path}-${index}`} item={item} />
          ))}
        </Flex>
      </Flex>
    </Card>
  );
}

export function HomologationChip({ item }: { item: Homologation }) {
  return (
    <Badge color={item.source === "model" ? "amber" : "green"} variant="soft" size="2">
      <s style={{ opacity: 0.6 }}>{item.original}</s>
      {" → "}
      <strong>{item.canonical}</strong>
    </Badge>
  );
}
