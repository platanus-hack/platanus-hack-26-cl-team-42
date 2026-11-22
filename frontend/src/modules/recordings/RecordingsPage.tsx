import { useState } from "react";
import { Card, Flex, Select, Text } from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { type Recording } from "./api";
import { usePatients } from "../patients/api";
import { PipelineView } from "../pipeline/PipelineView";
import { Recorder } from "./Recorder";

interface RecordingsPageProps {
  /** Dictado cuyo proceso (transcripción → informe) se está mostrando. */
  recordingId?: string;
}

export function RecordingsPage({ recordingId }: RecordingsPageProps) {
  const [patientId, setPatientId] = useState<number | undefined>();
  const navigate = useNavigate();
  // El dictado guardado ya se está procesando solo: se muestra el avance aquí mismo.
  const showProcess = (recording: Recording) => navigate({ to: "/recordings", search: { recording: recording.id } });

  return (
    <ModulePage stepId="recordings" connected>
      <Card size="3">
        <Flex direction="column" gap="5">
          <PatientPicker value={patientId} onChange={setPatientId} />
          <Recorder patientId={patientId} onSaved={showProcess} />
        </Flex>
      </Card>

      {recordingId && (
        <PipelineView
          key={recordingId}
          recordingId={recordingId}
          onMissing={() => navigate({ to: "/recordings", search: {}, replace: true })}
        />
      )}
    </ModulePage>
  );
}

/** El paciente se elige entre los asignados antes de grabar: identifica de quién es el dictado y el informe. */
function PatientPicker({ value, onChange }: { value: number | undefined; onChange: (id: number) => void }) {
  const { data: patients = [], isPending } = usePatients();
  const selected = patients.find((patient) => patient.id === value);

  return (
    <Flex direction="column" gap="1">
      <Text as="label" size="2" weight="medium">
        Paciente
      </Text>
      <Flex gap="3" wrap="wrap" align="center">
        <Select.Root value={selected ? String(selected.id) : undefined} onValueChange={(id) => onChange(Number(id))}>
          <Select.Trigger
            placeholder={isPending ? "Cargando pacientes…" : patients.length === 0 ? "No tienes pacientes asignados" : "Elige un paciente asignado"}
            style={{ minWidth: 300 }}
          />
          <Select.Content>
            {patients.map((patient) => (
              <Select.Item key={patient.id} value={String(patient.id)}>
                {patient.reference}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Flex>
      <Text size="1" color="gray">
        Solo aparecen los pacientes que tienes asignados (los que registras en «Mis pacientes» o te traspasa otro usuario). El
        audio se nombra solo con tu cuenta, el profesional y la hora.
      </Text>
    </Flex>
  );
}
