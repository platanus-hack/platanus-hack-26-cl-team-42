import type { ReactNode } from "react";
import { Badge, Button, Flex, Heading, Text, Tooltip } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { getWorkflowStep, type WorkflowStep, type WorkflowStepId } from "../config/workflow";
import { ArrowIcon, StepIcon } from "./icons";

interface ModulePageProps {
  stepId: WorkflowStepId;
  children: ReactNode;
  /** El módulo ya habla con su backend: oculta la insignia «Sin conexión». */
  connected?: boolean;
}

/** Marco común de los módulos: encabezado del paso, contenido y navegación del flujo. */
export function ModulePage({ stepId, children, connected = false }: ModulePageProps) {
  const { steps, index, step, previous, next } = getWorkflowStep(stepId);

  return (
    <Flex direction="column" gap="6" p={{ initial: "4", md: "6" }} style={{ maxWidth: "1100px" }}>
      <Flex direction="column" gap="4">
        <StepProgress steps={steps} currentIndex={index} />

        <Flex align="start" gap="4">
          <span className="step-icon">
            <StepIcon id={stepId} size={18} />
          </span>
          <Flex direction="column" gap="1" style={{ minWidth: 0 }}>
            <Text size="2" color="gray" weight="medium">
              Paso {index + 1} de {steps.length}
            </Text>
            <Flex align="center" gap="3" wrap="wrap">
              <Heading size="7" style={{ letterSpacing: "-0.01em" }}>
                {step.label}
              </Heading>
              {!connected && (
                <Tooltip content="Los controles se habilitarán al conectar el backend de este módulo.">
                  <Badge color="gray" variant="surface" radius="full">
                    Sin conexión
                  </Badge>
                </Tooltip>
              )}
            </Flex>
            <Text color="gray" size="3">
              {step.summary}
            </Text>
          </Flex>
        </Flex>
      </Flex>

      {children}

      <Flex
        justify="between"
        align="center"
        gap="3"
        wrap="wrap"
        pt="5"
        style={{ borderTop: "1px solid var(--gray-a4)" }}
      >
        {previous ? (
          <Link to={previous.path} style={{ textDecoration: "none" }}>
            <Button variant="soft" color="gray" size="3" radius="full">
              <ArrowIcon direction="left" />
              {previous.label}
            </Button>
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link to={next.path} style={{ textDecoration: "none" }}>
            <Button variant="solid" size="3" radius="full">
              {next.label}
              <ArrowIcon direction="right" />
            </Button>
          </Link>
        ) : (
          <span />
        )}
      </Flex>
    </Flex>
  );
}

/** Barra de progreso: un segmento por paso, con los anteriores completados. */
function StepProgress({ steps, currentIndex }: { steps: readonly WorkflowStep[]; currentIndex: number }) {
  return (
    <Flex gap="1" aria-hidden="true">
      {steps.map((step, index) => (
        <span
          key={step.id}
          className="progress-segment"
          data-state={index < currentIndex ? "done" : index === currentIndex ? "current" : "pending"}
          title={step.label}
        />
      ))}
    </Flex>
  );
}
