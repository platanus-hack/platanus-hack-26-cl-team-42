import type { ReactNode } from "react";
import { Badge, Text } from "@radix-ui/themes";
import { Link, useMatchRoute } from "@tanstack/react-router";
import { VISIBLE_STEPS } from "../config/workflow";
import { useOpenConflictCount } from "../modules/reconciliation/api";
import { StepIcon } from "./icons";

/** Etiquetas cortas: en un teléfono cada pestaña mide un cuarto del ancho. */
const SHORT_LABEL: Record<string, string> = {
  patients: "Pacientes",
  reconciliation: "Conflictos",
  "official-form": "Registro",
  handoff: "Traspaso",
};

/**
 * Barra de pestañas inferior, al alcance del pulgar: solo aparece en teléfono y tablet vertical
 * (en pantallas anchas la navegación queda en la barra superior).
 */
export function BottomNav() {
  const openConflicts = useOpenConflictCount();

  return (
    <nav className="bottom-nav" aria-label="Navegación inferior" style={{ ["--tabs" as string]: VISIBLE_STEPS.length }}>
      {VISIBLE_STEPS.map((step) => (
        <Tab key={step.id} to={step.path} label={SHORT_LABEL[step.id] ?? step.label} badge={step.id === "reconciliation" ? openConflicts : 0}>
          <StepIcon id={step.id} size={22} />
        </Tab>
      ))}
    </nav>
  );
}

function Tab({
  to,
  label,
  badge,
  children,
}: {
  to: string;
  label: string;
  badge: number;
  children: ReactNode;
}) {
  const matchRoute = useMatchRoute();
  const active = !!matchRoute({ to, fuzzy: to !== "/" });

  return (
    <Link to={to} className="bottom-nav__tab" data-active={active || undefined} aria-current={active ? "page" : undefined}>
      <span className="bottom-nav__icon">
        {children}
        {badge > 0 && (
          <Badge color="orange" variant="solid" radius="full" size="1" className="bottom-nav__badge" aria-label={`${badge} conflictos por resolver`}>
            {badge}
          </Badge>
        )}
      </span>
      <Text size="1" weight={active ? "bold" : "regular"}>
        {label}
      </Text>
    </Link>
  );
}
