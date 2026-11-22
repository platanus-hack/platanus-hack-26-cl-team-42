import { useCallback, useEffect, useRef, useState } from "react";
import {
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
} from "@radix-ui/themes";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMediaQuery } from "../../components/useMediaQuery";
import { EmptyState } from "../../components/EmptyState";
import { ModulePage } from "../../components/ModulePage";
import { SelectableListItem } from "../../components/SelectableListItem";
import { StepIcon } from "../../components/icons";
import { Toast, type ToastMessage } from "../../components/Toast";
import {
  PROCESSING_STEPS,
  patientKeys,
  usePatientSummary,
  usePatients,
  useTransferPatient,
  type PatientWithCount,
} from "../patients/api";
import { ChartCard, type ChartedNotice } from "../charting/ChartCard";
import { useChartMark } from "../episode/api";
import { useOpenConflictCount, useReconciliations } from "../reconciliation/api";
import { Recorder } from "../recordings/Recorder";
import { PatientSummaryView, type PatientTab } from "../reports/PatientSummaryView";
import { ReportView } from "../reports/ReportView";
import { reportKeys, useReports, type Report } from "../reports/api";
import { reportTitle } from "../reports/format";
import { useRetryTranscription } from "../transcription/api";
import { filterInbox, formatLastVisit, inboxRowState, sortInbox } from "./inbox";

export interface InboxSearch {
  patient?: string;
  /** Informe abierto en el detalle del paciente. */
  report?: string;
  /** Sección del informe a destacar (enlaces del asistente y del resumen). */
  section?: string;
  /** Cierre de turno: la lista muestra solo los pacientes con atenciones por pasar a la ficha. */
  chart?: boolean;
}

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

/** «Mis pacientes»: bandeja con los pacientes asignados a la izquierda y el elegido a la derecha. */
export function InboxPage({ search }: { search: InboxSearch }) {
  const navigate = useNavigate();
  const { data = [], isPending, isError, error } = usePatients();
  const patients = sortInbox(data);
  const charting = search.chart === true;
  const toChart = patients.filter((patient) => patient.pendingChart > 0);
  const listed = charting ? toChart : patients;
  const openConflicts = useOpenConflictCount();
  // En tablet horizontal y escritorio, lista y detalle lado a lado; en teléfono y tablet vertical,
  // un panel a la vez: la lista y, al tocar un paciente, su detalle con un botón para volver.
  const wide = useMediaQuery("(min-width: 900px)");
  const chosen = patients.find((patient) => String(patient.id) === search.patient);
  const selected = chosen ?? (wide ? listed[0] : undefined);
  const showList = wide || !chosen;
  // El modo de cierre de turno se conserva al moverse entre pacientes.
  const go = (next: InboxSearch) => navigate({ to: "/", search: { ...next, chart: charting || undefined } });
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const closeToast = useCallback(() => setToast(null), []);
  useProcessingToasts(data, setToast);
  const unmark = useChartMark("unmark");

  /** Tras confirmar, avisa con «Deshacer» y, en cierre de turno, sigue con el próximo paciente. */
  const onCharted = (patient: PatientWithCount, notice: ChartedNotice) => {
    setToast({
      id: Date.now(),
      text: `Registro de ${patient.name} marcado como pasado a la ficha.`,
      action: { label: "Deshacer", onClick: () => unmark.mutate(notice) },
    });
    if (!charting) return;
    const index = toChart.findIndex((item) => item.id === patient.id);
    const next = [...toChart.slice(index + 1), ...toChart.slice(0, index)].find((item) => item.id !== patient.id);
    go(next ? { patient: String(next.id) } : {});
  };

  return (
    <ModulePage stepId="patients">
      <Toast message={toast} onClose={closeToast} />
      {showList ? (
        openConflicts > 0 && (
          <Flex align="center" gap="2" wrap="wrap">
            <Text size="2" color="amber" weight="medium">
              {openConflicts} {openConflicts === 1 ? "conflicto tuyo" : "conflictos tuyos"} por resolver
            </Text>
            <Button size="1" variant="soft" color="amber" asChild>
              <Link to="/reconciliation" search={{}}>
                Resolver
              </Link>
            </Button>
          </Flex>
        )
      ) : (
        <Flex>
          <Button size="3" variant="soft" color="gray" onClick={() => go({})}>
            ← Volver a la lista
          </Button>
        </Flex>
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
        <Grid columns={wide ? "280px 1fr" : "1"} gap="5" align="start">
          {showList && (
            <PatientInbox
              patients={listed}
              loading={isPending}
              toChart={toChart.length}
              charting={charting}
              onChartingChange={(next) =>
                navigate({ to: "/", search: { patient: search.patient, chart: next || undefined } })
              }
              selected={wide ? selected?.id : undefined}
              query={patientQuery}
              onQueryChange={setPatientQuery}
              onSelect={(id) => go({ patient: String(id) })}
            />
          )}
          {selected && (
            <Box style={{ minWidth: 0 }}>
              <PatientDetail
                key={selected.id}
                patient={selected}
                search={search}
                go={go}
                showContext={!wide}
                onCharted={(notice) => onCharted(selected, notice)}
              />
            </Box>
          )}
        </Grid>
      )}
    </ModulePage>
  );
}

/** Avisa cuando un dictado termina de procesarse (listo para validar o con error), en cualquier paciente. */
function useProcessingToasts(patients: PatientWithCount[], notify: (message: ToastMessage) => void) {
  const previous = useRef<Map<number, PatientWithCount["inboxStatus"]> | null>(null);
  useEffect(() => {
    const before = previous.current;
    previous.current = new Map(patients.map((patient) => [patient.id, patient.inboxStatus]));
    if (!before) return;
    const finished = patients.filter(
      (patient) => before.get(patient.id) === "processing" && (patient.inboxStatus === "review" || patient.inboxStatus === "failed"),
    );
    const last = finished[finished.length - 1];
    if (!last) return;
    notify({
      id: Date.now(),
      text:
        last.inboxStatus === "review"
          ? `El informe de ${last.name} está listo para validar.`
          : `No se pudo procesar el dictado de ${last.name}.`,
    });
  }, [patients, notify]);
}

interface PatientInboxProps {
  patients: PatientWithCount[];
  loading: boolean;
  /** Cuántos pacientes tienen atenciones tuyas por pasar a la ficha. */
  toChart: number;
  charting: boolean;
  onChartingChange: (charting: boolean) => void;
  selected: number | undefined;
  query: string;
  onQueryChange: (query: string) => void;
  onSelect: (id: number) => void;
}

/** La posición en la lista depende de la cama y el nombre. */
function PatientInbox({
  patients,
  loading,
  toChart,
  charting,
  onChartingChange,
  selected,
  query,
  onQueryChange,
  onSelect,
}: PatientInboxProps) {
  if (loading) return <Skeleton height="240px" />;
  const visiblePatients = filterInbox(patients, query);
  return (
    <Flex direction="column" gap="2">
      <Heading size="3" as="h2" id="assigned-patients-heading">
        {charting ? "Por pasar a la ficha" : "Pacientes asignados"}{" "}
        <Text size="2" color="gray" weight="regular">{patients.length}</Text>
      </Heading>
      {(toChart > 0 || charting) && (
        <Button
          size="2"
          variant={charting ? "solid" : "soft"}
          aria-pressed={charting}
          onClick={() => onChartingChange(!charting)}
        >
          {charting ? "Ver todos los pacientes" : `Pasar a ficha · ${toChart}`}
        </Button>
      )}
      {charting && patients.length === 0 && (
        <Text size="2" color="gray" role="status">
          Ya pasaste todo a la ficha. Buen cierre de turno.
        </Text>
      )}
      {patients.length > 0 && (
        <TextField.Root
          type="search"
          aria-label="Buscar pacientes por nombre o cama"
          placeholder="Buscar por nombre o cama"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      )}
      {query.trim() && (
        <Text size="1" color="gray" role="status">
          {visiblePatients.length === 0
            ? "No se encontraron pacientes."
            : `${visiblePatients.length} de ${patients.length} pacientes`}
        </Text>
      )}
      {visiblePatients.length > 0 && (
        <Flex direction="column" gap="2" role="list" aria-labelledby="assigned-patients-heading">
          {visiblePatients.map((patient) => (
            <InboxRow key={patient.id} patient={patient} selected={patient.id === selected} onSelect={onSelect} />
          ))}
        </Flex>
      )}
    </Flex>
  );
}

/** Fila compacta: nombre, cama, la señal principal como insignia y las demás debajo. */
function InboxRow({ patient, selected, onSelect }: { patient: PatientWithCount; selected: boolean; onSelect: (id: number) => void }) {
  const row = inboxRowState(patient);
  return (
    <SelectableListItem
      title={patient.name}
      meta={patient.bed.trim() || "Sin cama"}
      subtitle={row.secondary.join(" · ")}
      badge={{ label: row.badge.text, color: row.badge.color, loading: row.badge.processing }}
      accent={row.color === "red" || row.color === "amber" ? row.color : undefined}
      selected={selected}
      onSelect={() => onSelect(patient.id)}
    >
      <PatientContext patient={patient} />
    </SelectableListItem>
  );
}

/**
 * Contexto del paciente: última visita, versión oficial y conflictos con su acción. En escritorio va en
 * la fila seleccionada; en teléfono, bajo el encabezado del detalle (nunca en ambos lugares).
 */
function PatientContext({ patient }: { patient: PatientWithCount }) {
  const { data: summary } = usePatientSummary(patient.id);
  const { data: reconciliations = [] } = useReconciliations();
  const open = reconciliations.filter((item) => item.patientId === patient.id && item.status === "open");
  const target = open.find((item) => item.conflicts.some((conflict) => conflict.status === "open" && conflict.myRole !== null)) ?? open[0];
  const mine = patient.myOpenConflicts;
  const facts = [
    `Última visita: ${formatLastVisit(patient.lastDictationAt)}`,
    patient.visitPriority !== "unknown" ? patient.visitPriorityLabel : null,
    patient.criticality !== "unknown" ? `Criticidad ${patient.criticalityLabel.toLowerCase()}` : null,
    patient.pendingTasks > 0 ? `${patient.pendingTasks} ${patient.pendingTasks === 1 ? "tarea pendiente" : "tareas pendientes"}` : null,
  ];

  return (
    <Flex direction="column" gap="1">
      {facts.map((fact) => fact && <Text key={fact} size="1" color="gray">{fact}</Text>)}
      {summary && (
        <Text size="1" color="gray">
          {summary.version > 0 ? <>Versión oficial <strong>n.º {summary.version}</strong></> : "Sin versión oficial"}
        </Text>
      )}
      {patient.openConflicts > 0 && (
        <Flex align="center" justify="between" gap="2" wrap="wrap" mt="1">
          <Text size="1" color="amber" weight="medium">
            {patient.openConflicts} {patient.openConflicts === 1 ? "conflicto" : "conflictos"} entre informes
            {mine > 0 ? (mine === patient.openConflicts ? "" : ` · ${mine} ${mine === 1 ? "tuyo" : "tuyos"}`) : " · de otros"}
          </Text>
          <Button size="1" color={mine > 0 ? "amber" : "gray"} variant="soft" asChild>
            <Link to="/reconciliation" search={target ? { id: target.id } : {}}>
              {mine > 0 ? "Resolver" : "Consultar"}
            </Link>
          </Button>
        </Flex>
      )}
    </Flex>
  );
}

interface PatientDetailProps {
  patient: PatientWithCount;
  search: InboxSearch;
  go: (next: InboxSearch) => void;
  /** En teléfono la fila no se ve junto al detalle: el contexto va bajo el encabezado. */
  showContext: boolean;
  onCharted: (notice: ChartedNotice) => void;
}

function PatientDetail({ patient, search, go, showContext, onCharted }: PatientDetailProps) {
  const [tab, setTab] = useState<PatientTab>("summary");
  // Incluye tus borradores (para «Informe por validar»); el historial solo muestra los guardados.
  const { data: allReports = [], isPending } = useReports(patient.id, true);
  const reports = allReports.filter((report) => report.status === "done");
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
      {showContext && <PatientContext patient={patient} />}
      <ProcessingNotice patient={patient} />
      {toValidate.map((report) => (
        <ValidationPrompt key={report.id} report={report} onOpen={() => openReport(report.id)} />
      ))}
      {patient.pendingChart > 0 && <ChartCard patientId={patient.id} onCharted={onCharted} />}
      <PatientSummaryView
        patientId={patient.id}
        reports={reports}
        reportsLoading={isPending}
        onOpenReport={openReport}
        tab={tab}
        onTabChange={setTab}
      />
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
    <Callout.Root color="amber" variant="surface">
      <Flex justify="between" align="center" gap="3" wrap="wrap" style={{ width: "100%" }}>
        <Callout.Text>
          No se pudo procesar tu último dictado.{retryId ? "" : " Vuelve a grabarlo."}
          {retry.isError && ` (${retry.error.message})`}
        </Callout.Text>
        {retryId && (
          <Button
            size="1"
            variant="soft"
            color="amber"
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
