import type { ReactNode } from "react";
import { Avatar, Badge, Button, Flex, IconButton, Popover, Separator, Text } from "@radix-ui/themes";
import { Link, useMatchRoute, useNavigate } from "@tanstack/react-router";
import { VISIBLE_STEPS } from "../config/workflow";
import { accountTypeLabel, useAccountProfile } from "../modules/account/api";
import { useOpenConflictCount } from "../modules/reconciliation/api";
import { professionLabel } from "../modules/recordings/professions";
import { useAuth } from "../services/auth";
import { DemoAccountSwitcher } from "./DemoAccountSwitcher";
import { StepIcon } from "./icons";

/**
 * Barra superior fija: marca, navegación y cuenta. Reemplaza al menú lateral para que la app
 * se use cómoda en teléfono o tablet: en pantallas angostas la navegación se desliza hacia el lado.
 */
export function AppHeader({ userEmail }: { userEmail: string }) {
  const openConflicts = useOpenConflictCount();

  return (
    <header className="app-header">
      <Flex asChild align="center" gap="2" className="app-header__brand">
        <Link to="/" style={{ textDecoration: "none", color: "inherit" }} aria-label="Mis pacientes">
          <img src="/logo.png" className="brand-mark" alt="" aria-hidden="true" />
          <Text size="3" weight="bold">
            Flujo médico
          </Text>
        </Link>
      </Flex>
      <Flex className="app-header__user">
        <AccountMenu userEmail={userEmail} />
      </Flex>

      <Flex asChild gap="2" className="app-header__nav">
        <nav aria-label="Principal">
          {VISIBLE_STEPS.map((step) => (
            <NavPill key={step.id} to={step.path} label={step.label} badge={step.id === "reconciliation" ? openConflicts : 0}>
              <StepIcon id={step.id} size={16} />
            </NavPill>
          ))}
        </nav>
      </Flex>
    </header>
  );
}

function NavPill({
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
    <Link to={to} style={{ textDecoration: "none", flexShrink: 0 }} aria-current={active ? "page" : undefined}>
      <Button
        size="3"
        radius="full"
        variant={active ? "soft" : "ghost"}
        color={active ? undefined : "gray"}
        highContrast={active}
        style={{ margin: 0 }}
      >
        {children}
        <span>{label}</span>
        {badge > 0 && (
          <Badge color="orange" variant="solid" radius="full" aria-label={`${badge} conflictos por resolver`}>
            {badge}
          </Badge>
        )}
      </Button>
    </Link>
  );
}

function AccountMenu({ userEmail }: { userEmail: string }) {
  const { logout } = useAuth();
  const { data: profile } = useAccountProfile();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await logout?.();
      navigate({ to: "/login" });
    } catch (err) {
      console.error("Error logging out:", err);
    }
  };

  return (
    <Popover.Root>
      <Popover.Trigger>
        <IconButton size="3" radius="full" variant="ghost" aria-label="Cuenta">
          <Avatar size="2" fallback={(userEmail.charAt(0) || "?").toUpperCase()} radius="full" />
        </IconButton>
      </Popover.Trigger>
      <Popover.Content style={{ width: "min(280px, 90vw)" }}>
        <Flex direction="column" gap="2">
          <Text size="2" weight="medium" truncate>
            {profile?.name || profile?.email || userEmail}
          </Text>
          {profile && (
            <Flex gap="2" wrap="wrap">
              <Badge color={profile.admin_url ? "indigo" : "gray"}>{accountTypeLabel(profile)}</Badge>
              {profile.profession && <Badge color="gray">{professionLabel(profile.profession)}</Badge>}
            </Flex>
          )}
          <Separator size="4" />
          <Popover.Close>
            <Button asChild variant="ghost" color="gray" size="3" style={{ justifyContent: "flex-start" }}>
              <Link to="/profile">Mi perfil</Link>
            </Button>
          </Popover.Close>
          <ExternalLink href="/-docs/" label="Documentación" />
          {profile?.admin_url && <ExternalLink href={profile.admin_url} label="Administración" />}
          <Separator size="4" />
          <Button variant="soft" color="red" size="3" onClick={handleLogout}>
            Cerrar sesión
          </Button>
          <DemoAccountSwitcher />
        </Flex>
      </Popover.Content>
    </Popover.Root>
  );
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <Button asChild variant="ghost" color="gray" size="3" style={{ justifyContent: "flex-start" }}>
      <a href={href} target="_blank" rel="noopener noreferrer">
        {label} ↗
      </a>
    </Button>
  );
}
