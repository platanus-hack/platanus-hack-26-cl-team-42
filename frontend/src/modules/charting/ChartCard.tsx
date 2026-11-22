import { useMemo } from "react";
import { Button, Callout, Card, Flex, Heading, Skeleton, Text, TextArea } from "@radix-ui/themes";
import { useChartMark, useEpisodeRecords, useTeam } from "../episode/api";
import { CopyButton } from "../episode/components";
import { pendingChartEncounters, renderChartText } from "../episode/record";

export interface ChartedNotice {
  episodeId: string;
  encounterIds: string[];
}

/**
 * «Por pasar a la ficha»: el texto de tus atenciones de este paciente que aún no pegas en la
 * ficha institucional. Copiar no marca nada; recién «Ya lo pegué» las da por pasadas.
 */
export function ChartCard({ patientId, onCharted }: { patientId: number; onCharted: (notice: ChartedNotice) => void }) {
  const { data: records, isPending: recordsPending, error } = useEpisodeRecords();
  const { data: team, isPending: teamPending } = useTeam();
  const mark = useChartMark("mark");
  const episodeId = String(patientId);
  const record = records?.find(({ episode }) => episode.id === episodeId);
  const meId = team?.meId;
  const encounters = useMemo(
    () => (record && meId ? pendingChartEncounters(record, meId) : []),
    [record, meId],
  );
  const text = useMemo(
    () => (record && meId ? renderChartText(record, encounters, meId) : ""),
    [record, encounters, meId],
  );

  if (recordsPending || teamPending) return <Skeleton height="120px" />;
  if (error) {
    return (
      <Callout.Root color="red" variant="surface">
        <Callout.Text>No se pudo armar el texto para la ficha: {error.message}</Callout.Text>
      </Callout.Root>
    );
  }
  if (encounters.length === 0) return null;

  const encounterIds = encounters.map((encounter) => encounter.id);
  // `mutateAsync` y no el `onSuccess` de `mutate`: al refrescarse la bandeja esta tarjeta se
  // desmonta, y React Query descarta los callbacks de un componente desmontado.
  const confirm = () =>
    mark
      .mutateAsync({ episodeId, encounterIds })
      .then(() => onCharted({ episodeId, encounterIds }))
      .catch(() => undefined); // el error ya se muestra con `mark.isError`

  return (
    <Card style={{ boxShadow: "inset 3px 0 0 var(--accent-9), 0 0 0 1px var(--gray-a5)" }}>
      <Flex direction="column" gap="3">
        <Flex direction="column">
          <Heading size="3" as="h3">
            Por pasar a la ficha
          </Heading>
          <Text size="2" color="gray">
            {encounters.length === 1 ? "1 atención tuya" : `${encounters.length} atenciones tuyas`} sin pasar a la
            ficha institucional. Copia el texto, pégalo en la ficha y confirma.
          </Text>
        </Flex>
        <TextArea
          readOnly
          value={text}
          rows={8}
          aria-label="Texto para la ficha institucional"
          style={{ fontFamily: "var(--code-font-family)" }}
        />
        {mark.isError && (
          <Text size="1" color="red">
            No se pudo marcar como pasado: {mark.error.message}
          </Text>
        )}
        <Flex gap="2" justify="end" wrap="wrap">
          <CopyButton text={text} label="Copiar" />
          <Button loading={mark.isPending} onClick={confirm}>
            Ya lo pegué
          </Button>
        </Flex>
      </Flex>
    </Card>
  );
}
