import { Badge, Box, Button, Card, Flex, Heading, Table, Text, Tooltip } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { StepIcon } from "../../components/icons";
import { useRecordings, type RecordingStatus } from "./api";

/** Alturas (%) de la forma de onda decorativa; sin audio todavía. */
const WAVE_HEIGHTS = [30, 45, 25, 60, 40, 80, 55, 35, 70, 90, 50, 30, 65, 45, 25, 75, 40, 55, 30, 20, 45, 60, 35, 25];

const STATUS_LABEL: Record<RecordingStatus, { label: string; color: "gray" | "green" | "red" }> = {
  uploading: { label: "Subiendo", color: "gray" },
  ready: { label: "Lista", color: "green" },
  failed: { label: "Fallida", color: "red" },
};

export function RecordingsPage() {
  const { data: recordings = [], isPending } = useRecordings();

  return (
    <ModulePage stepId="recordings">
      <Card size="3">
        <Flex direction="column" align="center" gap="5" py="6">
          <Flex align="center" justify="center" style={{ width: 96, height: 96 }}>
            <Tooltip content="Disponible al conectar el backend">
              <span className="record-ring" style={{ borderRadius: 999 }}>
                <Button size="4" color="red" variant="solid" radius="full" disabled style={{ width: 80, height: 80 }}>
                  <StepIcon id="recordings" size={28} />
                </Button>
              </span>
            </Tooltip>
          </Flex>
          <Text size="7" weight="medium" style={{ fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}>
            00:00
          </Text>
          <Box className="waveform" aria-hidden="true">
            {WAVE_HEIGHTS.map((height, index) => (
              <span key={index} style={{ height: `${height}%` }} />
            ))}
          </Box>
          <Text size="2" color="gray" align="center">
            Un audio por dictado o consulta, asociado al profesional que lo graba.
          </Text>
        </Flex>
      </Card>

      <Flex direction="column" gap="3">
        <Heading size="4">Grabaciones</Heading>
        {!isPending && recordings.length === 0 ? (
          <EmptyState
            title="Aún no hay grabaciones"
            description="Las grabaciones aparecerán aquí cuando se conecte el módulo."
          />
        ) : (
          <Table.Root variant="surface">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>Profesional</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Duración</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Fecha</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Estado</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {recordings.map((recording) => (
                <Table.Row key={recording.id}>
                  <Table.Cell>{recording.professionalName}</Table.Cell>
                  <Table.Cell>{recording.durationSeconds}s</Table.Cell>
                  <Table.Cell>{recording.createdAt}</Table.Cell>
                  <Table.Cell>
                    <Badge color={STATUS_LABEL[recording.status].color} variant="soft">
                      {STATUS_LABEL[recording.status].label}
                    </Badge>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        )}
      </Flex>
    </ModulePage>
  );
}
