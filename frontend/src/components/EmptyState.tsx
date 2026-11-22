import type { ReactNode } from "react";
import { Card, Flex, Text } from "@radix-ui/themes";
import { InboxIcon } from "./icons";

interface EmptyStateProps {
  title: string;
  description: string;
  /** Acción principal bajo el texto (p. ej. «Nuevo paciente»). */
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <Card size="3" style={{ background: "var(--color-panel-solid)" }}>
      <Flex direction="column" align="center" gap="3" py="6" px="4">
        <span className="step-icon" style={{ width: 48, height: 48, borderRadius: 14 }}>
          <InboxIcon size={22} />
        </span>
        <Flex direction="column" align="center" gap="1">
          <Text weight="medium" size="3">
            {title}
          </Text>
          <Text size="2" color="gray" align="center" style={{ maxWidth: 380 }}>
            {description}
          </Text>
        </Flex>
        {action}
      </Flex>
    </Card>
  );
}
