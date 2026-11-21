import { useState } from "react";
import { Button, Callout, Flex, Text, TextField } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import { professionLabel } from "../recordings/professions";
import { sectionLabel } from "../templates/recordFields";
import { reportTitle } from "./format";
import { useAskReports, type AssistantAnswer } from "./api";

interface Exchange {
  question: string;
  answer: AssistantAnswer;
}

interface AssistantPanelProps {
  /** Si se indica, la consulta se limita a los informes de ese paciente. */
  patientId?: number;
  patientName?: string;
}

/** Consultas rápidas a los informes: cada respuesta cita el informe y la sección de donde sale. */
export function AssistantPanel({ patientId, patientName }: AssistantPanelProps) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const ask = useAskReports();

  const submit = () => {
    const text = question.trim();
    if (!text || ask.isPending) return;
    ask.mutate(
      { question: text, patientId },
      {
        onSuccess: (answer) => {
          setHistory((current) => [{ question: text, answer }, ...current]);
          setQuestion("");
        },
      },
    );
  };

  return (
    <CollapsibleSection
      title="Pregúntale a los informes"
      detail={patientId !== undefined ? `Solo ${patientName ?? "este paciente"}` : "Todos tus pacientes"}
      open={history.length > 0}
    >
      <Flex direction="column" gap="3">
        <Text size="1" color="gray">
          Responde con los informes guardados y cada dato trae su referencia.
        </Text>
        <Flex gap="2">
          <TextField.Root
            style={{ flex: 1 }}
            placeholder="Ej.: ¿Qué drogas vasoactivas usa y en qué dosis?"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit();
            }}
          />
          <Button loading={ask.isPending} disabled={!question.trim()} onClick={submit}>
            Preguntar
          </Button>
        </Flex>

        {ask.isError && (
          <Callout.Root color="red" size="1">
            <Callout.Text>{ask.error.message}</Callout.Text>
          </Callout.Root>
        )}

        {history.map((exchange, index) => (
          <Answer key={`${exchange.question}-${index}`} exchange={exchange} />
        ))}
      </Flex>
    </CollapsibleSection>
  );
}

function Answer({ exchange }: { exchange: Exchange }) {
  const { answer, references } = exchange.answer;
  return (
    <Flex direction="column" gap="2" p="3" style={{ background: "var(--gray-a2)", borderRadius: "var(--radius-3)" }}>
      <Text size="2" weight="medium">
        {exchange.question}
      </Text>
      <Text size="2" style={{ whiteSpace: "pre-wrap" }}>
        {answer}
      </Text>
      {references.length > 0 && (
        <Flex direction="column" gap="1">
          <Text size="1" color="gray" weight="medium">
            Referencias
          </Text>
          {references.map((reference) => (
            <Text key={`${reference.reportId}-${reference.section}`} size="1">
              <Link
                to="/reports"
                search={{
                  patient: reference.patientId !== null ? String(reference.patientId) : "all",
                  report: reference.reportId,
                  section: reference.section,
                  view: "reports",
                }}
              >
                {reportTitle(reference.sequence, reference.profession)} · {reference.patientName} ·{" "}
                {sectionLabel(reference.section)}
              </Link>
              {reference.detail && <> — «{reference.detail}»</>}
              <span style={{ color: "var(--gray-11)" }}> ({professionLabel(reference.profession)}, {reference.authorName})</span>
            </Text>
          ))}
        </Flex>
      )}
    </Flex>
  );
}
