import { useState } from "react";
import { Badge, Button, Callout, Card, Dialog, Flex, Grid, Heading, Tabs, Text, TextField } from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { usePatients, useTransferPatient, type PatientWithCount } from "../patients/api";
import { AssistantPanel } from "./AssistantPanel";
import { PatientSummaryView } from "./PatientSummaryView";
import { ReportView, StatusBadge } from "./ReportView";
import { reportTitle } from "./format";
import { useReports, type Report } from "./api";

export interface ReportsSearch {
  /** Id del paciente o «all» para ver los informes de todos tus pacientes. */
  patient?: string;
  report?: string;
  /** Sección del informe a destacar (enlaces del asistente y del resumen). */
  section?: string;
  view?: "summary" | "reports";
}

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

export function ReportsPage({ search }: { search: ReportsSearch }) {
  const navigate = useNavigate();
  const { data: patients = [], isPending: patientsPending } = usePatients();

  // Al entrar se muestra el resumen del primer paciente; «all» junta los informes de todos.
  const patientParam = search.patient ?? (search.report ? "all" : patients[0] ? String(patients[0].id) : "all");
  const patient = patients.find((item) => String(item.id) === patientParam);
  const view = patient ? (search.view ?? (search.report || search.section ? "reports" : "summary")) : "reports";
  const go = (next: ReportsSearch) => navigate({ to: "/reports", search: next });

  return (
    <ModulePage stepId="reports" connected>
      <Grid columns={{ initial: "1", md: "260px 1fr" }} gap="4">
        <PatientList
          patients={patients}
          loading={patientsPending}
          selected={patient?.id}
          onSelect={(id) => go(id === undefined ? { patient: "all", view: "reports" } : { patient: String(id) })}
        />

        <Flex direction="column" gap="4" style={{ minWidth: 0 }}>
          <AssistantPanel patientId={patient?.id} patientName={patient?.name} />

          {patient ? (
            <Card>
              <Flex direction="column" gap="3">
                <PatientHeader patient={patient} />
                <Tabs.Root value={view} onValueChange={(value) => go({ patient: String(patient.id), view: value as ReportsSearch["view"] })}>
                  <Tabs.List>
                    <Tabs.Trigger value="summary">Resumen</Tabs.Trigger>
                    <Tabs.Trigger value="reports">Informes ({patient.reportCount})</Tabs.Trigger>
                  </Tabs.List>
                </Tabs.Root>
                {view === "summary" ? (
                  <PatientSummaryView patientId={patient.id} onOpenReports={() => go({ patient: String(patient.id), view: "reports" })} />
                ) : (
                  <ReportBrowser patientId={patient.id} search={search} onSelect={(id) => go({ patient: String(patient.id), report: id, view: "reports" })} />
                )}
              </Flex>
            </Card>
          ) : (
            <Card>
              <ReportBrowser patientId={undefined} search={search} onSelect={(id) => go({ patient: "all", report: id, view: "reports" })} />
            </Card>
          )}
        </Flex>
      </Grid>
    </ModulePage>
  );
}

interface PatientListProps {
  patients: PatientWithCount[];
  loading: boolean;
  selected: number | undefined;
  onSelect: (id: number | undefined) => void;
}

function PatientList({ patients, loading, selected, onSelect }: PatientListProps) {
  return (
    <Flex direction="column" gap="2">
      <Heading size="4">Mis pacientes</Heading>
      <Button variant={selected === undefined ? "solid" : "soft"} onClick={() => onSelect(undefined)} style={{ justifyContent: "start" }}>
        Todos los informes
      </Button>
      {!loading && patients.length === 0 ? (
        <EmptyState
          title="Sin pacientes asignados"
          description="Los pacientes vienen de otro sistema o te los traspasa otro usuario. Cuando tengas uno asignado aparecerá aquí."
        />
      ) : (
        patients.map((patient) => (
          <Button
            key={patient.id}
            variant={patient.id === selected ? "solid" : "soft"}
            onClick={() => onSelect(patient.id)}
            style={{ justifyContent: "space-between", height: "auto", padding: "8px 12px" }}
          >
            <Flex direction="column" align="start" style={{ textAlign: "left" }}>
              <span>{patient.name}</span>
              <Text size="1">{[patient.bed, patient.identifier].filter(Boolean).join(" · ") || "Sin cama"}</Text>
            </Flex>
            <Badge variant="surface" radius="full">
              {patient.reportCount}
            </Badge>
          </Button>
        ))
      )}
    </Flex>
  );
}

function PatientHeader({ patient }: { patient: PatientWithCount }) {
  return (
    <Flex justify="between" align="start" gap="3" wrap="wrap">
      <Flex direction="column">
        <Heading size="4">{patient.name}</Heading>
        <Text size="2" color="gray">
          {[patient.identifier, patient.bed].filter(Boolean).join(" · ") || "Sin identificador"}
        </Text>
      </Flex>
      <TransferDialog patient={patient} />
    </Flex>
  );
}

/** Los pacientes no se crean aquí: solo se traspasan a otro usuario, que pasa a verlos. */
function TransferDialog({ patient }: { patient: PatientWithCount }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const navigate = useNavigate();
  const transfer = useTransferPatient();

  const submit = () =>
    transfer.mutate(
      { patientId: patient.id, toEmail: email.trim() },
      {
        onSuccess: () => {
          setOpen(false);
          setEmail("");
          // El paciente deja de estar asignado a ti: se vuelve a la vista general.
          void navigate({ to: "/reports", search: {} });
        },
      },
    );

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) transfer.reset();
      }}
    >
      <Dialog.Trigger>
        <Button variant="soft" color="gray">
          Traspasar paciente
        </Button>
      </Dialog.Trigger>
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

interface ReportBrowserProps {
  patientId: number | undefined;
  search: ReportsSearch;
  onSelect: (reportId: string) => void;
}

/** Los informes (de todos los profesionales asociados al paciente) y el detalle del elegido. */
function ReportBrowser({ patientId, search, onSelect }: ReportBrowserProps) {
  const { data: reports = [], isPending, isError, error } = useReports(patientId);
  const selected = reports.find((report) => report.id === search.report) ?? reports[0];

  if (isError) {
    return (
      <Callout.Root color="red">
        <Callout.Text>No se pudieron cargar los informes: {error.message}</Callout.Text>
      </Callout.Root>
    );
  }
  if (!isPending && reports.length === 0) {
    return (
      <EmptyState
        title="Aún no hay informes"
        description="Cada dictado que grabes se transcribe, se parsea y se homologa solo; su informe aparecerá aquí."
      />
    );
  }
  return (
    <Grid columns={{ initial: "1", lg: "240px 1fr" }} gap="4">
      <Flex direction="column" gap="2">
        {reports.map((report) => (
          <ReportButton key={report.id} report={report} selected={report.id === selected?.id} showPatient={patientId === undefined} onSelect={onSelect} />
        ))}
      </Flex>
      <div style={{ minWidth: 0 }}>
        {selected && <ReportView report={selected} focusSection={selected.id === search.report ? search.section : undefined} />}
      </div>
    </Grid>
  );
}

interface ReportButtonProps {
  report: Report;
  selected: boolean;
  showPatient: boolean;
  onSelect: (reportId: string) => void;
}

function ReportButton({ report, selected, showPatient, onSelect }: ReportButtonProps) {
  return (
    <Button
      variant={selected ? "solid" : "soft"}
      onClick={() => onSelect(report.id)}
      style={{ justifyContent: "space-between", height: "auto", padding: "8px 12px" }}
    >
      <Flex direction="column" align="start" style={{ textAlign: "left" }}>
        <span>{reportTitle(report.sequence, report.profession)}</span>
        <Text size="1">
          {showPatient && `${report.patient?.name ?? report.patientReference} · `}
          {report.authorName} · {DATE_FORMAT.format(new Date(report.recordedAt))}
        </Text>
      </Flex>
      {report.status !== "done" && <StatusBadge report={report} />}
    </Button>
  );
}
