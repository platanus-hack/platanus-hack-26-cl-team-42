import type { CSSProperties, ReactNode } from "react";
import { Badge, Box, Flex, Reset, Spinner, Text } from "@radix-ui/themes";

type ItemColor = "red" | "amber" | "green" | "gray";

interface SelectableListItemProps {
  title: string;
  /** Texto gris bajo el título (contexto o señales secundarias). */
  subtitle?: ReactNode;
  /** Dato corto junto al título, p. ej. la cama. */
  meta?: string;
  badge?: { label: string; color: ItemColor; loading?: boolean };
  /** Franja izquierda: solo para lo que pide atención (rojo o ámbar). */
  accent?: "red" | "amber";
  selected: boolean;
  onSelect: () => void;
  /** Contexto que se despliega bajo la fila seleccionada. */
  children?: ReactNode;
}

/** Fila de una lista lateral (Mis pacientes, Conflictos): título, insignia y, si está elegida, su contexto. */
export function SelectableListItem({ title, subtitle, meta, badge, accent, selected, onSelect, children }: SelectableListItemProps) {
  const style = accent ? ({ "--list-item-accent": `var(--${accent}-9)` } as CSSProperties) : undefined;
  return (
    <Box role="listitem" className="list-item" data-selected={selected || undefined} style={style}>
      <Reset>
        <button type="button" className="list-item__trigger" aria-current={selected || undefined} aria-expanded={selected} onClick={onSelect}>
          <Flex justify="between" align="start" gap="2">
            <Flex direction="column" gap="1" style={{ minWidth: 0 }}>
              <Flex align="baseline" gap="2" style={{ minWidth: 0 }}>
                <Text size="2" weight="medium" truncate>
                  {title}
                </Text>
                {meta && (
                  <Text size="1" color="gray" style={{ whiteSpace: "nowrap" }}>
                    {meta}
                  </Text>
                )}
              </Flex>
              {subtitle && (
                <Text size="1" color="gray" truncate>
                  {subtitle}
                </Text>
              )}
            </Flex>
            {badge && (
              <Badge color={badge.color} variant="soft" radius="full" style={{ flexShrink: 0 }}>
                {badge.loading && <Spinner size="1" />}
                {badge.label}
              </Badge>
            )}
          </Flex>
        </button>
      </Reset>
      {selected && children && (
        <Box px="3" pb="3">
          {children}
        </Box>
      )}
    </Box>
  );
}
