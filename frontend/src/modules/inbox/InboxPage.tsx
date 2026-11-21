import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Box,
  Button,
  Callout,
  Card,
  Dialog,
  DropdownMenu,
  Flex,
  Grid,
  Heading,
  IconButton,
  Progress,
  Skeleton,
  Spinner,
  Text,
  TextField,
  Tooltip,
} from "@radix-ui/themes";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import { EmptyState } from "../../components/EmptyState";
import { StepIcon } from "../../components/icons";
import { PROCESSING_STEPS, patientKeys, usePatients, useTransferPatient, type PatientWithCount } from "../patients/api";
import { useReconciliations } from "../reconciliation/api";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { Recorder } from "../recordings/Recorder";
import { AssistantPanel } from "../reports/AssistantPanel";
import { PatientSummaryView } from "../reports/PatientSummaryView";
import { ReportView, StatusBadge } from "../reports/ReportView";
import { reportKeys, useReports, type Report } from "../reports/api";
import { reportTitle } from "../reports/format";
import { useRetryTranscription } from "../transcription/api";
import { CRITICALITY_META, INBOX_STATUS, VISIT_META, formatLastVisit, needsAction, sortInbox } from "./inbox";

export interface InboxSearch {
  patient?: string;
  /** Informe abierto en el detalle del paciente. */
  report?: string;
  /** Sección del informe a destacar (enlaces del asistente y del resumen). */
  section?: string;
}

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

/** «Mis pacientes»: bandeja con los pacientes asignados a la izquierda y el elegido a la derecha. */
export function InboxPage({ search }: { search: InboxSearch }) {
  const navigate = useNavigate();
  const { data = [], isPending, isError, error } = usePatients();
  const patients = sortInbox(data);
  const { data: reconciliations = [] } = useReconciliations();
  const openConflicts = reconciliations
    .filter((item) => item.status === "open")
    .reduce(
      (total, item) =>
        total + item.conflicts.filter((conflict) => conflict.status === "open" && conflict.myRole !== null).length,
      0,
    );
  const selected = patients.find((patient) => String(patient.id) === search.patient) ?? patients[0];
  const go = (next: InboxSearch) => navigate({ to: "/", search: next });

  return (
    <Flex direction="column" gap="4" p={{ initial: "4", md: "6" }} style={{ maxWidth: 1280 }}>
      <Heading size="6">Mis pacientes</Heading>
      {openConflicts > 0 && (
        <Callout.Root color="orange">
          <Flex align="center" justify="between" gap="3" wrap="wrap">
            <Callout.Text>
              Hay {openConflicts} {openConflicts === 1 ? "conflicto" : "conflictos"} entre informes por resolver en los que
              participas.
            </Callout.Text>
            <Link to="/reconciliation" search={{}}>
              <Button size="1" color="orange">
                Resolver conflictos
              </Button>
            </Link>
          </Flex>
        </Callout.Root>
      )}
      {isError ? (
        <Callout.Root color="red">
          <Callout.Text>No se pudieron cargar tus pacientes: {error.message}</Callout.Text>
        </Callout.Root>
      ) : !isPending && patients.length === 0 ? (
        <EmptyState
          title="Sin pacientes asignados"
          description="Los pacientes vienen de otro sistema o te los traspasa otro usuario. Cuando tengas uno asignado aparecerá aquí."
        />
      ) : (
        <Grid columns={{ initial: "1", md: "320px 1fr" }} gap={{ initial: "5", md: "8" }} align="start">
          <Box
            pr={{ initial: "0", md: "6" }}
            style={{ borderRight: "1px solid var(--gray-a5)", alignSelf: "stretch" }}
          >
            <PatientInbox
              patients={patients}
              loading={isPending}
              selected={selected?.id}
              onSelect={(id) => go({ patient: String(id) })}
            />
          </Box>
          <Box style={{ minWidth: 0 }}>
            {selected && <PatientDetail key={selected.id} patient={selected} search={search} go={go} />}
          </Box>
        </Grid>
      )}
    </Flex>
  );
}

interface PatientInboxProps {
  patients: PatientWithCount[];
  loading: boolean;
  selected: number | undefined;
  onSelect: (id: number) => void;
}

function PatientInbox({ patients, loading, selected, onSelect }: PatientInboxProps) {
  if (loading) return <Skeleton height="240px" />;
  return (
    <Flex direction="column" gap="1" role="list" aria-label="Mis pacientes">
      <Text size="1" color="gray" mb="1">
        {patients.length} {patients.length === 1 ? "asignado" : "asignados"}
      </Text>
      {patients.map((patient) => (
        <InboxRow key={patient.id} patient={patient} selected={patient.id === selected} onSelect={onSelect} />
      ))}
    </Flex>
  );
}

function InboxRow({ patient, selected, onSelect }: { patient: PatientWithCount; selected: boolean; onSelect: (id: number) => void }) {
  const status = INBOX_STATUS[patient.inboxStatus];
  const urgent = needsAction(patient.inboxStatus);
  const visit = VISIT_META[patient.visitPriority];
  return (
    <Button
      role="listitem"
      variant="ghost"
      color="gray"
      aria-current={selected || undefined}
      onClick={() => onSelect(patient.id)}
      style={{
        display: "block",
        width: "100%",
        height: "auto",
        margin: 0,
        padding: "10px 12px",
        textAlign: "left",
        borderRadius: "var(--radius-3)",
        color: "var(--gray-12)",
        background: selected ? "var(--gray-a3)" : undefined,
        boxShadow: urgent ? `inset 3px 0 0 var(--${status.color}-9)` : undefined,
      }}
    >
      <Flex justify="between" align="center" gap="2">
        <Text size="2" weight={urgent || selected ? "bold" : "regular"} truncate>
          {patient.name}
        </Text>
        <Badge color={CRITICALITY_META[patient.criticality].color} variant={patient.criticality === "critical" ? "solid" : "soft"} size="1">
          {patient.criticality === "unknown" ? "Sin clasificar" : patient.criticalityLabel}
        </Badge>
      </Flex>
      <Flex align="center" gap="1" mt="1">
        <Text size="1" color="gray">
          {patient.bed || "Sin cama"}
        </Text>
        {/* «Al día» solo dice algo si ya hubo dictados. */}
        {(patient.inboxStatus !== "up_to_date" || patient.lastDictationAt) && (
          <Text size="1" color={status.color ?? "gray"} weight={urgent ? "medium" : "regular"}>
            ·{" "}
            {patient.inboxStatus === "processing" && <Spinner size="1" style={{ display: "inline-block", marginRight: 4 }} />}
            {patient.inboxStatus === "processing" && patient.processingLabel
              ? `${patient.processingLabel} · ${patient.processingStep}/${PROCESSING_STEPS}`
              : status.label}
          </Text>
        )}
      </Flex>
      {patient.openConflicts > 0 && (
        <Flex mt="2">
          <Badge color="orange" variant={patient.myOpenConflicts > 0 ? "solid" : "soft"} size="1">
            ⚠ {patient.openConflicts} {patient.openConflicts === 1 ? "conflicto" : "conflictos"}
            {patient.myOpenConflicts === 0 && " · de otros"}
          </Badge>
        </Flex>
      )}
      <Flex justify="between" align="center" gap="2" mt="2">
        <Flex direction="column">
          <Text size="1" color={visit.color} weight={visit.bold ? "bold" : "regular"}>
            {patient.visitPriorityLabel}
          </Text>
          <Text size="1" color="gray">
            Última visita: {formatLastVisit(patient.lastDictationAt)}
          </Text>
        </Flex>
        <Tooltip content={`${patient.pendingTasks} ${patient.pendingTasks === 1 ? "tarea pendiente" : "tareas pendientes"}`}>
          <Badge
            color={patient.pendingTasks > 0 ? "amber" : "gray"}
            variant={patient.pendingTasks > 0 ? "solid" : "soft"}
            radius="full"
            size="2"
            aria-label={`${patient.pendingTasks} tareas pendientes`}
          >
            {patient.pendingTasks}
          </Badge>
        </Tooltip>
      </Flex>
    </Button>
  );
}

interface PatientDetailProps {
  patient: PatientWithCount;
  search: InboxSearch;
  go: (next: InboxSearch) => void;
}

function PatientDetail({ patient, search, go }: PatientDetailProps) {
  // Incluye tus borradores (para «Informe por validar»); el historial solo muestra los guardados.
  const { data: allReports = [], isPending } = useReports(patient.id, true);
  const reports = allReports.filter((report) => report.status === "done");
  const [historyOpen, setHistoryOpen] = useState(false);
  const queryClient = useQueryClient();
  // Al terminar de procesarse un dictado aparece (o cambia) su informe.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: [...reportKeys, patient.id] });
  }, [patient.inboxStatus, patient.id, queryClient]);
  const patientParam = String(patient.id);
  const openReport = (reportId: string) => go({ patient: patientParam, report: reportId });

  if (search.report) {
    const report = allReports.find((item) => item.id === search.report);
    return (
      <Flex direction="column" gap="4">
        <Flex>
          <Button variant="ghost" color="gray" onClick={() => go({ patient: patientParam })}>
            ← Volver a {patient.name}
          </Button>
        </Flex>
        {report ? (
          <ReportView report={report} focusSection={search.section} />
        ) : isPending ? (
          <Skeleton height="240px" />
        ) : (
          <EmptyState title="Informe no disponible" description="El informe ya no está entre los de este paciente." />
        )}
      </Flex>
    );
  }

  const toValidate = allReports.filter((report) => report.canEdit && report.status === "review");
  return (
    <Flex direction="column" gap="4">
      <PatientHeader patient={patient} />
      <ProcessingNotice patient={patient} />
      <ConflictNotice patient={patient} />
      {toValidate.map((report) => (
        <ValidationPrompt key={report.id} report={report} onOpen={() => openReport(report.id)} />
      ))}
      <PatientSummaryView patientId={patient.id} onOpenReports={() => setHistoryOpen(true)} />
      <EvidencePanel patientId={patient.id} />
      <CollapsibleSection title="Historial de informes" detail={String(reports.length)} open={historyOpen}>
        <ReportHistory reports={reports} onOpen={openReport} />
      </CollapsibleSection>
      <AssistantPanel patientId={patient.id} patientName={patient.name} />
    </Flex>
  );
}

function PatientHeader({ patient }: { patient: PatientWithCount }) {
  const [transferring, setTransferring] = useState(false);
  return (
    <Flex justify="between" align="start" gap="3" wrap="wrap">
      <Flex direction="column">
        <Heading size="5">{patient.name}</Heading>
        <Text size="2" color="gray">
          {[patient.bed, patient.identifier].filter(Boolean).join(" · ") || "Sin identificador"}
        </Text>
      </Flex>
      <Flex gap="2" align="center">
        <RecordDialog patient={patient} />
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <IconButton variant="soft" color="gray" aria-label="Más acciones">
              ⋯
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item onSelect={() => setTransferring(true)}>Traspasar paciente</DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </Flex>
      <TransferDialog patient={patient} open={transferring} onOpenChange={setTransferring} />
    </Flex>
  );
}

/** El grabador en un modal: no se cierra por error con un dictado en curso o sin guardar. */
function RecordDialog({ patient }: { patient: PatientWithCount }) {
  const [open, setOpen] = useState(false);
  const [unsaved, setUnsaved] = useState(false);
  const onUnsavedChange = useCallback((value: boolean) => setUnsaved(value), []);

  const close = () => {
    if (unsaved && !window.confirm("¿Descartar el dictado sin guardar?")) return;
    setOpen(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <Dialog.Trigger>
        <Button>
          <StepIcon id="recordings" size={16} />
          Grabar dictado
        </Button>
      </Dialog.Trigger>
      <Dialog.Content maxWidth="560px" onInteractOutside={(event) => event.preventDefault()}>
        <Dialog.Title>Dictado · {patient.name}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          {[patient.bed, patient.identifier].filter(Boolean).join(" · ")}
        </Dialog.Description>
        <Recorder patientId={patient.id} onSaved={() => setOpen(false)} onUnsavedChange={onUnsavedChange} />
        <Flex justify="end" mt="4">
          <Button variant="soft" color="gray" onClick={close}>
            Cerrar
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}

/** Aviso de los conflictos abiertos del paciente, con un acceso directo a resolverlos. */
function ConflictNotice({ patient }: { patient: PatientWithCount }) {
  const { data: reconciliations = [] } = useReconciliations();
  if (patient.openConflicts === 0) return null;
  const open = reconciliations.find((item) => item.patientId === patient.id && item.status === "open");
  const mine = patient.myOpenConflicts;
  return (
    <Callout.Root color="orange">
      <Flex align="center" justify="between" gap="3" wrap="wrap" style={{ width: "100%" }}>
        <Callout.Text>
          <strong>
            {patient.openConflicts} {patient.openConflicts === 1 ? "conflicto" : "conflictos"} entre informes por resolver
          </strong>
          {mine > 0 ? ` (${mine} ${mine === 1 ? "es tuyo" : "son tuyos"}).` : ": los resuelven quienes los reportaron."}
        </Callout.Text>
        <Link to="/reconciliation" search={open ? { id: open.id } : {}}>
          <Button size="1" color="orange" variant={mine > 0 ? "solid" : "soft"}>
            {mine > 0 ? "Resolver" : "Ver"}
          </Button>
        </Link>
      </Flex>
    </Callout.Root>
  );
}

function ProcessingNotice({ patient }: { patient: PatientWithCount }) {
  const retry = useRetryTranscription();
  const queryClient = useQueryClient();

  if (patient.inboxStatus === "processing") {
    return (
      <Callout.Root color="gray" variant="surface">
        <Callout.Icon>
          <Spinner size="1" />
        </Callout.Icon>
        <Flex direction="column" gap="2" style={{ width: "100%" }}>
          <Callout.Text>
            <strong>{patient.processingLabel ?? "Procesando tu último dictado"}</strong>
            {patient.processingStep !== null && ` · etapa ${patient.processingStep} de ${PROCESSING_STEPS}`}. Cuando el
            informe esté listo aparecerá aquí para validarlo.
          </Callout.Text>
          {patient.processingStep !== null && <Progress value={patient.processingStep} max={PROCESSING_STEPS} size="1" />}
        </Flex>
      </Callout.Root>
    );
  }
  if (patient.inboxStatus !== "failed") return null;

  const retryId = patient.retryRecordingId;
  return (
    <Callout.Root color="red" variant="surface">
      <Flex justify="between" align="center" gap="3" wrap="wrap" style={{ width: "100%" }}>
        <Callout.Text>
          No se pudo procesar tu último dictado.{retryId ? "" : " Vuelve a grabarlo."}
          {retry.isError && ` (${retry.error.message})`}
        </Callout.Text>
        {retryId && (
          <Button
            size="1"
            variant="soft"
            color="red"
            loading={retry.isPending}
            onClick={() =>
              retry.mutate(retryId, { onSuccess: () => void queryClient.invalidateQueries({ queryKey: patientKeys }) })
            }
          >
            Reintentar
          </Button>
        )}
      </Flex>
    </Callout.Root>
  );
}

function ValidationPrompt({ report, onOpen }: { report: Report; onOpen: () => void }) {
  return (
    <Card style={{ boxShadow: "inset 3px 0 0 var(--amber-9), 0 0 0 1px var(--gray-a5)" }}>
      <Flex justify="between" align="center" gap="3" wrap="wrap">
        <Flex direction="column">
          <Text size="2" weight="bold">
            Informe por validar
          </Text>
          <Text size="1" color="gray">
            {reportTitle(report.sequence, report.profession)} · tu dictado del {DATE_FORMAT.format(new Date(report.recordedAt))}
          </Text>
        </Flex>
        <Button onClick={onOpen}>Revisar y validar</Button>
      </Flex>
    </Card>
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
          {report.status !== "done" && <StatusBadge report={report} />}
        </Button>
      ))}
    </Flex>
  );
}

interface TransferDialogProps {
  patient: PatientWithCount;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Los pacientes no se crean aquí: solo se traspasan a otro usuario, que pasa a verlos. */
function TransferDialog({ patient, open, onOpenChange }: TransferDialogProps) {
  const [email, setEmail] = useState("");
  const navigate = useNavigate();
  const transfer = useTransferPatient();

  const submit = () =>
    transfer.mutate(
      { patientId: patient.id, toEmail: email.trim() },
      {
        onSuccess: () => {
          onOpenChange(false);
          setEmail("");
          // El paciente deja de estar asignado a ti: se vuelve a la bandeja.
          void navigate({ to: "/", search: {} });
        },
      },
    );

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) transfer.reset();
      }}
    >
      <Dialog.Content maxWidth="440px">
        <Dialog.Title>Traspasar a {patient.name}</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          El paciente pasa a la cuenta que indiques y deja de estar asignado a ti. Quien lo recibe verá sus informes
          guardados.
        </Dialog.Description>
        <Flex direction="column" gap="3" mt="3">
          <TextField.Root
            type="email"
            placeholder="Correo del profesional que lo recibe"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          {transfer.isError && (
            <Callout.Root color="red" size="1">
              <Callout.Text>{transfer.error.message}</Callout.Text>
            </Callout.Root>
          )}
        </Flex>
        <Flex gap="3" justify="end" mt="4">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Cancelar
            </Button>
          </Dialog.Close>
          <Button disabled={!email.trim()} loading={transfer.isPending} onClick={submit}>
            Traspasar
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
