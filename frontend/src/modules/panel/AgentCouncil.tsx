import { useState } from "react";
import { Badge, Button, Callout, Card, CheckboxGroup, Flex, Heading, Spinner, Text, TextArea } from "@radix-ui/themes";
import { PROFESSIONS } from "../recordings/professions";
import { isRunning, useOpenPanel, usePanels, type Panel, type PanelRecommendation, type PanelTurn } from "./api";

const CONFIDENCE: Record<PanelRecommendation["confianza"], { label: string; color: "green" | "amber" | "gray" }> = {
  alta: { label: "Confianza alta", color: "green" },
  media: { label: "Confianza media", color: "amber" },
  baja: { label: "Confianza baja", color: "gray" },
};

/**
 * Consejo de agentes: cada profesional del caso tiene un agente que opina con su rol y su
 * experiencia, discuten por rondas y un agente final recoge todo y recomienda. Parte de un
 * conflicto (`conflictId`) o de una pregunta libre sobre un paciente (`patientId`).
 */
export function AgentCouncil({
  conflictId,
  patientId,
  canLaunch,
}: {
  conflictId?: string;
  patientId?: number;
  canLaunch: boolean;
}) {
  const { data: panels = [] } = usePanels({ conflictId, patientId: conflictId ? undefined : patientId });
  const open = useOpenPanel();
  const [question, setQuestion] = useState("");
  const [showReasoning, setShowReasoning] = useState(false);
  const [areas, setAreas] = useState<string[]>([]);
  const latest = panels[0];
  const running = latest !== undefined && isRunning(latest);
  const freeQuestion = conflictId === undefined;

  const launch = () =>
    open.mutate(
      { conflictId, patientId, question: question.trim(), areas: freeQuestion ? areas : [] },
      { onSuccess: () => setQuestion("") },
    );

  return (
    <Card variant="surface">
      <Flex direction="column" gap="3">
        <Flex justify="between" align="center" gap="2" wrap="wrap">
          <Heading size="3">Consejo de agentes</Heading>
          {latest && <Status panel={latest} />}
        </Flex>
        <Text size="2" color="gray">
          {freeQuestion
            ? "Plantea una pregunta médica sobre este paciente: un agente por cada profesional de las áreas elegidas opina con su criterio y su experiencia, y un agente final recomienda."
            : "Somete esta discrepancia a los agentes de todos los profesionales de las áreas involucradas: opinan, se responden entre sí y un agente final recomienda."}{" "}
          Es un apoyo a la decisión, no la reemplaza.
        </Text>

        {latest?.status === "done" && latest.recommendation && (
          <Flex direction="column" gap="3">
            <Flex>
              <Button
                size="2"
                variant="soft"
                color="gray"
                aria-expanded={showReasoning}
                onClick={() => setShowReasoning((value) => !value)}
              >
                {showReasoning ? "▾" : "▸"} Razonamiento de agentes
              </Button>
            </Flex>
            {showReasoning && <Result panel={latest} recommendation={latest.recommendation} />}
          </Flex>
        )}
        {latest?.status === "failed" && (
          <Callout.Root color="red" size="1">
            <Callout.Text>{latest.error || "No se pudo completar la discusión."}</Callout.Text>
          </Callout.Root>
        )}
        {running && (
          <Flex align="center" gap="2">
            <Spinner />
            <Text size="2">Los agentes están discutiendo… esto toma un momento.</Text>
          </Flex>
        )}

        {canLaunch && !running && (
          <Flex direction="column" gap="2">
            {freeQuestion && (
              <Flex direction="column" gap="1">
                <Text size="1" color="gray" weight="medium">
                  Áreas que opinan (si no eliges, las que atienden a este paciente)
                </Text>
                <CheckboxGroup.Root size="1" value={areas} onValueChange={setAreas}>
                  <Flex gap="3" wrap="wrap">
                    {PROFESSIONS.map((profession) => (
                      <CheckboxGroup.Item key={profession.value} value={profession.value}>
                        {profession.label}
                      </CheckboxGroup.Item>
                    ))}
                  </Flex>
                </CheckboxGroup.Root>
              </Flex>
            )}
            <TextArea
              size="1"
              placeholder={freeQuestion ? "Tu pregunta médica sobre este paciente" : "Pregunta específica (opcional)"}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={1500}
            />
            <Flex>
              <Button
                size="2"
                variant={latest ? "soft" : "solid"}
                disabled={freeQuestion && question.trim() === ""}
                loading={open.isPending}
                onClick={launch}
              >
                {latest ? "Volver a consultar al consejo" : "Consultar al consejo de agentes"}
              </Button>
            </Flex>
          </Flex>
        )}
        {open.isError && (
          <Text size="2" color="red">
            {open.error.message}
          </Text>
        )}
      </Flex>
    </Card>
  );
}

function Status({ panel }: { panel: Panel }) {
  if (isRunning(panel)) return <Badge color="amber" variant="soft">En discusión</Badge>;
  if (panel.status === "failed") return <Badge color="red" variant="soft">Falló</Badge>;
  return (
    <Badge color="green" variant="soft">
      Con recomendación
    </Badge>
  );
}

function Result({ panel, recommendation }: { panel: Panel; recommendation: PanelRecommendation }) {
  const [showDiscussion, setShowDiscussion] = useState(false);
  const confidence = CONFIDENCE[recommendation.confianza];
  return (
    <Flex direction="column" gap="3">
      <Text size="2" color="gray">
        Pregunta: {panel.question}
      </Text>
      <Callout.Root color="green" size="1">
        <Flex direction="column" gap="2">
          <Flex align="center" gap="2" wrap="wrap">
            <Text size="2" weight="bold">
              Recomendación del agente final
            </Text>
            <Badge color={confidence.color} variant="soft" size="1">
              {confidence.label}
            </Badge>
          </Flex>
          {recommendation.resumen && <Callout.Text>{recommendation.resumen}</Callout.Text>}
          <Callout.Text>
            <strong>{recommendation.recomendacion}</strong>
          </Callout.Text>
        </Flex>
      </Callout.Root>
      <PointList title="Acuerdos" items={recommendation.acuerdos} />
      <PointList title="Desacuerdos" items={recommendation.desacuerdos} />
      <PointList title="Siguientes pasos" items={recommendation.siguientes_pasos} />
      <Text size="1" color="gray">
        {recommendation.aviso}
      </Text>
      <Flex>
        <Button size="1" variant="ghost" color="gray" onClick={() => setShowDiscussion((value) => !value)}>
          {showDiscussion ? "Ocultar la discusión" : `Ver la discusión (${panel.turns.length} intervenciones)`}
        </Button>
      </Flex>
      {showDiscussion && <Discussion turns={panel.turns} />}
    </Flex>
  );
}

function PointList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Flex direction="column" gap="1">
      <Text size="2" weight="medium">
        {title}
      </Text>
      {items.map((item) => (
        <Text key={item} size="2">
          • {item}
        </Text>
      ))}
    </Flex>
  );
}

function Discussion({ turns }: { turns: PanelTurn[] }) {
  const rounds = [...new Set(turns.map((turn) => turn.round))].sort((a, b) => a - b);
  return (
    <Flex direction="column" gap="3">
      {rounds.map((round) => (
        <Flex key={round} direction="column" gap="2">
          <Text size="1" color="gray" weight="medium">
            {round === 1 ? "Ronda 1 · opinión inicial" : `Ronda ${round} · réplica`}
          </Text>
          {turns
            .filter((turn) => turn.round === round)
            .map((turn) => (
              <Flex
                key={`${round}-${turn.author}`}
                direction="column"
                gap="1"
                p="3"
                style={{ borderRadius: "var(--radius-3)", background: "var(--gray-a2)" }}
              >
                <Text size="2" weight="medium">
                  {turn.author}
                </Text>
                {turn.stance && (
                  <Text size="1" color="gray">
                    Postura: {turn.stance}
                  </Text>
                )}
                <Text size="2">{turn.body}</Text>
              </Flex>
            ))}
        </Flex>
      ))}
    </Flex>
  );
}
