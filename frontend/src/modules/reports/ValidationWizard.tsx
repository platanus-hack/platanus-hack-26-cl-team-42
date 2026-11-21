import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Progress, Text } from "@radix-ui/themes";
import { SectionBlock } from "./SectionBlock";
import { useAcknowledgeAlert, useValidateReport, useValidateTopic, type EvidenceAlert, type Report } from "./api";
import type { PendingSection } from "./pending";

interface ValidationWizardProps {
  report: Report;
  pending: PendingSection[];
  busy: boolean;
}

/**
 * Validación por ventanas: un tema a la vez, con «Validar y continuar» o «Volver».
 * Tras el último tema, una ventana final resume y permite guardar el informe (que ya no se edita).
 */
export function ValidationWizard({ report, pending, busy }: ValidationWizardProps) {
  const { topics, validatedTopics } = report;
  const firstOpen = topics.findIndex((topic) => !validatedTopics.includes(topic.id));
  const [step, setStep] = useState(firstOpen === -1 ? topics.length : firstOpen);
  const validate = useValidateTopic();
  const save = useValidateReport();

  const onSummary = step >= topics.length;
  const topic = topics[Math.min(step, topics.length - 1)];
  const validatedCount = topics.filter((item) => validatedTopics.includes(item.id)).length;
  const allValidated = topics.length > 0 && validatedCount === topics.length;

  const validateAndContinue = () =>
    validate.mutate(
      { reportId: report.id, topicId: topic.id, validated: true },
      { onSuccess: () => setStep((current) => current + 1) },
    );

  if (topics.length === 0) return null;

  return (
    <Card variant="classic">
      <Flex direction="column" gap="4">
        <Flex direction="column" gap="2">
          <Flex justify="between" align="center" gap="3" wrap="wrap">
            <Text weight="medium">Validación del informe</Text>
            <Text size="2" color={allValidated ? "green" : "gray"}>
              {validatedCount} de {topics.length} temas validados
            </Text>
          </Flex>
          <Progress value={validatedCount} max={topics.length} color={allValidated ? "green" : undefined} />
          <Flex gap="2" wrap="wrap">
            {topics.map((item, index) => (
              <Badge
                key={item.id}
                color={validatedTopics.includes(item.id) ? "green" : index === step ? "indigo" : "gray"}
                variant={index === step ? "solid" : "soft"}
                style={{ cursor: "pointer" }}
                onClick={() => setStep(index)}
              >
                {validatedTopics.includes(item.id) ? "✓ " : ""}
                {item.label}
              </Badge>
            ))}
            <Badge
              color={onSummary ? "indigo" : "gray"}
              variant={onSummary ? "solid" : "soft"}
              style={{ cursor: "pointer" }}
              onClick={() => setStep(topics.length)}
            >
              Guardar
            </Badge>
          </Flex>
        </Flex>

        {report.evidenceAlerts.some((alert) => !alert.acknowledged) && (
          <Callout.Root color="red" size="1">
            <Callout.Text>
              <strong>
                {report.evidenceAlerts.filter((alert) => !alert.acknowledged).length} alerta(s) de evidencia por revisar:
              </strong>{" "}
              el informe contradice los exámenes del paciente. Aparecen en el tema correspondiente.
            </Callout.Text>
          </Callout.Root>
        )}

        {onSummary ? (
          <SaveWindow
            report={report}
            allValidated={allValidated}
            busy={busy}
            saving={save.isPending}
            error={save.isError ? save.error.message : undefined}
            onBack={() => setStep(topics.length - 1)}
            onSave={() => save.mutate(report.id)}
            onGoTo={setStep}
          />
        ) : (
          <TopicWindow
            report={report}
            topicIndex={step}
            pending={pending}
            busy={busy}
            validating={validate.isPending}
            error={validate.isError ? validate.error.message : undefined}
            onBack={() => setStep((current) => Math.max(0, current - 1))}
            onNext={() => setStep((current) => current + 1)}
            onValidate={validateAndContinue}
          />
        )}
      </Flex>
    </Card>
  );
}

interface TopicWindowProps {
  report: Report;
  topicIndex: number;
  pending: PendingSection[];
  busy: boolean;
  validating: boolean;
  error: string | undefined;
  onBack: () => void;
  onNext: () => void;
  onValidate: () => void;
}

/** Una ventana: las secciones del tema, lo que falta y las opciones de validar o volver atrás. */
function TopicWindow({ report, topicIndex, pending, busy, validating, error, onBack, onNext, onValidate }: TopicWindowProps) {
  const topic = report.topics[topicIndex];
  const validated = report.validatedTopics.includes(topic.id);
  const topicPending = pending.filter((section) => topic.sections.includes(section.key));

  return (
    <Flex direction="column" gap="3">
      <Flex align="center" gap="2" wrap="wrap">
        <Text size="4" weight="medium">
          {topic.label}
        </Text>
        <Text size="2" color="gray">
          Tema {topicIndex + 1} de {report.topics.length}
        </Text>
        {validated && (
          <Badge color="green" variant="soft">
            Validado
          </Badge>
        )}
      </Flex>

      <EvidenceAlerts
        report={report}
        alerts={report.evidenceAlerts.filter((alert) => alert.topic === topic.id)}
      />

      {topicPending.length > 0 && !validated && (
        <Callout.Root color="amber" size="1">
          <Callout.Text>
            Hay información pendiente en este tema. Puedes completarla con texto o con un audio antes de validar, o
            validarlo tal como está.
          </Callout.Text>
        </Callout.Root>
      )}

      <Flex direction="column" gap="3">
        {topic.sections.map((key) => (
          <SectionBlock
            key={key}
            report={report}
            sectionKey={key}
            pendingFields={topicPending.find((section) => section.key === key)?.fields ?? []}
            canComplete={!validated}
            busy={busy}
          />
        ))}
      </Flex>

      {error && (
        <Text size="2" color="red">
          {error}
        </Text>
      )}

      <Flex justify="between" gap="3" wrap="wrap">
        <Button variant="soft" color="gray" disabled={topicIndex === 0} onClick={onBack}>
          Volver
        </Button>
        {validated ? (
          <Button variant="soft" onClick={onNext}>
            Siguiente
          </Button>
        ) : (
          <Button loading={validating} disabled={busy} onClick={onValidate}>
            Validar y continuar
          </Button>
        )}
      </Flex>
    </Flex>
  );
}

interface SaveWindowProps {
  report: Report;
  allValidated: boolean;
  busy: boolean;
  saving: boolean;
  error: string | undefined;
  onBack: () => void;
  onSave: () => void;
  onGoTo: (index: number) => void;
}

/** Ventana final: resumen de la validación y guardado definitivo del informe. */
function SaveWindow({ report, allValidated, busy, saving, error, onBack, onSave, onGoTo }: SaveWindowProps) {
  return (
    <Flex direction="column" gap="3">
      <Text size="4" weight="medium">
        Guardar el informe
      </Text>
      <Flex direction="column" gap="1">
        {report.topics.map((topic, index) => {
          const validated = report.validatedTopics.includes(topic.id);
          return (
            <Flex key={topic.id} justify="between" align="center" gap="3">
              <Text size="2">
                {validated ? "✓" : "○"} {topic.label}
              </Text>
              {!validated && (
                <Button size="1" variant="ghost" onClick={() => onGoTo(index)}>
                  Revisar
                </Button>
              )}
            </Flex>
          );
        })}
      </Flex>
      <EvidenceAlerts report={report} alerts={report.evidenceAlerts.filter((alert) => !alert.acknowledged)} />
      <Callout.Root color={allValidated ? "green" : "amber"} size="1">
        <Callout.Text>
          {allValidated
            ? "Todos los temas están validados. Al guardar, el informe queda disponible para el equipo del paciente y ya no se puede editar."
            : "Valida todos los temas para poder guardar el informe."}
        </Callout.Text>
      </Callout.Root>
      {error && (
        <Text size="2" color="red">
          {error}
        </Text>
      )}
      <Flex justify="between" gap="3" wrap="wrap">
        <Button variant="soft" color="gray" onClick={onBack}>
          Volver
        </Button>
        <Button loading={saving} disabled={!allValidated || busy} onClick={onSave}>
          Guardar informe
        </Button>
      </Flex>
    </Flex>
  );
}

/** Contradicciones del informe con los exámenes del paciente: se muestran y se dan por revisadas. */
function EvidenceAlerts({ report, alerts }: { report: Report; alerts: EvidenceAlert[] }) {
  const acknowledge = useAcknowledgeAlert();
  if (alerts.length === 0) return null;

  return (
    <Flex direction="column" gap="2" role="region" aria-label="Alertas de evidencia">
      {alerts.map((alert) => (
        <Callout.Root key={alert.id} color={alert.acknowledged ? "gray" : alert.severity === "high" ? "red" : "amber"} size="1">
          <Flex direction="column" gap="2" style={{ width: "100%" }}>
            <Callout.Text>
              <strong>{ALERT_LABEL[alert.kind]}:</strong> {alert.message}
            </Callout.Text>
            <Flex align="center" gap="2">
              {alert.acknowledged ? (
                <Badge color="green" variant="soft">
                  ✓ Revisada
                </Badge>
              ) : (
                <Button
                  size="1"
                  variant="soft"
                  color={alert.severity === "high" ? "red" : "amber"}
                  loading={acknowledge.isPending && acknowledge.variables?.alertId === alert.id}
                  onClick={() => acknowledge.mutate({ reportId: report.id, alertId: alert.id })}
                >
                  Marcar como revisada
                </Button>
              )}
              <Text size="1" color="gray">
                Corrige la sección o confirma que el informe es correcto.
              </Text>
            </Flex>
          </Flex>
        </Callout.Root>
      ))}
    </Flex>
  );
}

const ALERT_LABEL: Record<EvidenceAlert["kind"], string> = {
  value: "Contradice un examen",
  omission: "Resultado no mencionado",
  concept: "Contradicción con la evidencia",
};
