import { useEffect } from "react";
import { Button, Flex, IconButton, Text } from "@radix-ui/themes";

export interface ToastMessage {
  /** Cambia en cada aviso, para que el temporizador vuelva a empezar. */
  id: number;
  text: string;
  /** Acción opcional junto al texto (p. ej. «Deshacer»); al usarla se cierra el aviso. */
  action?: { label: string; onClick: () => void };
}

const DURATION_MS = 6000;

/** Aviso breve arriba a la derecha: se cierra solo a los pocos segundos o con la ×. */
export function Toast({ message, onClose }: { message: ToastMessage | null; onClose: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(onClose, DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [message, onClose]);

  if (!message) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      <Flex align="start" gap="3">
        <Text size="2" style={{ flex: 1 }}>
          {message.text}
        </Text>
        {message.action && (
          <Button
            size="1"
            variant="soft"
            onClick={() => {
              message.action?.onClick();
              onClose();
            }}
          >
            {message.action.label}
          </Button>
        )}
        <IconButton size="1" variant="ghost" color="gray" aria-label="Cerrar aviso" onClick={onClose}>
          ×
        </IconButton>
      </Flex>
    </div>
  );
}
