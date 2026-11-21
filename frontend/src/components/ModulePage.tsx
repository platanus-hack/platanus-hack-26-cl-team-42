import type { ReactNode } from "react";
import { Flex, Heading, Text } from "@radix-ui/themes";
import { getWorkflowStep, type WorkflowStepId } from "../config/workflow";

interface ModulePageProps {
  stepId: WorkflowStepId;
  children: ReactNode;
  /** Ya no se usa: todos los módulos visibles hablan con su backend. */
  connected?: boolean;
}

/** Marco común de los módulos: un título breve y el contenido. La navegación vive en la barra superior. */
export function ModulePage({ stepId, children }: ModulePageProps) {
  const { step } = getWorkflowStep(stepId);

  return (
    <Flex direction="column" gap="4" p={{ initial: "3", sm: "4", md: "6" }} style={{ maxWidth: "1100px", margin: "0 auto" }}>
      <Flex direction="column" gap="1">
        <Heading size={{ initial: "5", md: "7" }} style={{ letterSpacing: "-0.01em" }}>
          {step.label}
        </Heading>
        <Text color="gray" size="2">
          {step.summary}
        </Text>
      </Flex>

      {children}
    </Flex>
  );
}
