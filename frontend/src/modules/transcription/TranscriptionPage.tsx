import { Button, Card, Flex, Grid, Heading, Select, Text, TextArea } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useTranscripts } from "./api";

export function TranscriptionPage() {
  const { data: transcripts = [], isPending } = useTranscripts();
  const selected = transcripts[0];

  return (
    <ModulePage stepId="transcription">
      <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Audios por transcribir</Heading>
          {!isPending && transcripts.length === 0 ? (
            <EmptyState
              title="Sin transcripciones"
              description="Los audios grabados aparecerán aquí para transcribirlos."
            />
          ) : (
            transcripts.map((transcript) => (
              <Card key={transcript.id}>
                <Text size="2">{transcript.id}</Text>
              </Card>
            ))
          )}
        </Flex>

        <Card>
          <Flex direction="column" gap="3">
            <Flex justify="between" align="center" gap="3" wrap="wrap">
              <Select.Root disabled defaultValue="es">
                <Select.Trigger placeholder="Idioma" />
                <Select.Content>
                  <Select.Item value="es">Español</Select.Item>
                  <Select.Item value="en">Inglés</Select.Item>
                </Select.Content>
              </Select.Root>
              <Button variant="soft" disabled>
                Transcribir
              </Button>
            </Flex>
            <TextArea
              size="3"
              rows={14}
              disabled
              placeholder="La transcripción del audio seleccionado aparecerá aquí, editable antes de continuar."
              value={selected?.text ?? ""}
            />
          </Flex>
        </Card>
      </Grid>
    </ModulePage>
  );
}
