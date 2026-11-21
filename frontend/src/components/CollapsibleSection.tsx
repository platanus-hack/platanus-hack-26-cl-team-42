import { useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Card, Flex, Text } from "@radix-ui/themes";

interface CollapsibleSectionProps {
  title: string;
  /** Texto corto a la derecha del título (p. ej. cuántos elementos tiene). */
  detail?: string;
  badge?: { label: string; color: "amber" | "gray" | "green" | "red" | "indigo" };
  /** Abre la sección por defecto o cuando pasa a `true` (p. ej. al seguir un enlace). */
  open?: boolean;
  id?: string;
  children: ReactNode;
}

/** Bloque plegado por defecto: muestra solo su encabezado hasta que se expande. */
export function CollapsibleSection({ title, detail, badge, open = false, id, children }: CollapsibleSectionProps) {
  const [expanded, setExpanded] = useState(open);

  useEffect(() => {
    if (open) setExpanded(true);
  }, [open]);

  return (
    <Card id={id} variant="surface" style={{ scrollMarginTop: 80 }}>
      <Flex direction="column" gap="3">
        <Button
          type="button"
          variant="ghost"
          color="gray"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          style={{ width: "100%", justifyContent: "space-between", height: "auto", padding: "4px 0", margin: 0 }}
        >
          <Flex align="center" gap="2">
            <Text aria-hidden="true" color="gray" style={{ width: 14 }}>
              {expanded ? "▾" : "▸"}
            </Text>
            <Text weight="medium">{title}</Text>
          </Flex>
          <Flex align="center" gap="2">
            {detail && (
              <Text size="1" color="gray">
                {detail}
              </Text>
            )}
            {badge && (
              <Badge color={badge.color} variant="soft">
                {badge.label}
              </Badge>
            )}
          </Flex>
        </Button>
        {expanded && children}
      </Flex>
    </Card>
  );
}
