import {
  Box,
  Flex,
  Button,
  Text,
  Avatar,
  Separator,
  ScrollArea,
  Popover,
} from "@radix-ui/themes";
import { Link, useMatchRoute, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useAuth } from "../services/auth";
import { DemoAccountSwitcher } from "./DemoAccountSwitcher";
import { VISIBLE_STEPS } from "../config/workflow";
import { HomeIcon, StepIcon } from "./icons";

interface SidebarProps {
  userEmail: string;
}

export function Sidebar({ userEmail }: SidebarProps) {
  const { logout } = useAuth();
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
    <Box
      style={{
        width: "250px",
        height: "100vh",
        borderRight: "1px solid var(--gray-a5)",
        backgroundColor: "var(--color-panel)",
        position: "fixed",
        left: 0,
        top: 0,
      }}
    >
      <Flex direction="column" style={{ height: "100%" }}>
        {/* Marca */}
        <Flex align="center" gap="3" px="4" pt="4" pb="3">
          <span className="brand-mark" aria-hidden="true">
            <HomeIcon size={18} />
          </span>
          <Flex direction="column">
            <Text size="3" weight="bold" style={{ lineHeight: 1.2 }}>
              Flujo médico
            </Text>
            <Text size="1" color="gray">
              Equipo multiprofesional
            </Text>
          </Flex>
        </Flex>

        {/* Navegación */}
        <ScrollArea style={{ flex: 1 }}>
          <Flex direction="column" gap="2" p="3">
            {VISIBLE_STEPS.map((step) => (
              <NavLinkButton
                key={step.id}
                to={step.path}
                label={step.label}
                icon={<StepIcon id={step.id} size={16} />}
              />
            ))}
          </Flex>
        </ScrollArea>

        {/* External links: the VitePress docs site and the Django admin,
            both served behind the ingress */}
        <Flex direction="column" gap="2" px="3" pb="2">
          <ExternalLinkButton href="/-docs/" label="Docs" />
          <ExternalLinkButton href="/-/admin/" label="Admin" />
        </Flex>

        <Separator size="4" />

        {/* User Profile */}
        <Box p="3">
          <Popover.Root>
            <Popover.Trigger>
              <Flex gap="3" align="center" style={{ cursor: "pointer" }}>
                <Avatar
                  size="2"
                  fallback={userEmail.charAt(0).toUpperCase()}
                  radius="full"
                />
                <Flex direction="column" gap="1">
                  <Text size="2" weight="medium">
                    {userEmail.split("@")[0]}
                  </Text>
                  <Text size="1" color="gray">
                    {userEmail}
                  </Text>
                </Flex>
              </Flex>
            </Popover.Trigger>
            <Popover.Content style={{ width: "260px" }}>
              <Flex direction="column" gap="2">
                <DemoAccountSwitcher />
                <Link to="/profile">
                  <Button
                    variant="ghost"
                    style={{ justifyContent: "flex-start", width: "100%" }}
                  >
                    Profile
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  style={{ justifyContent: "flex-start" }}
                >
                  Settings
                </Button>
                <Separator size="4" />
                <Button
                  variant="ghost"
                  color="red"
                  style={{ justifyContent: "flex-start" }}
                  onClick={handleLogout}
                >
                  Logout
                </Button>
              </Flex>
            </Popover.Content>
          </Popover.Root>
        </Box>
      </Flex>
    </Box>
  );
}

function NavLinkButton({ to, label, icon }: { to: string; label: string; icon: ReactNode }) {
  const matchRoute = useMatchRoute();
  const active = !!matchRoute({ to });

  return (
    <Link to={to} style={{ textDecoration: "none" }}>
      <Button
        variant={active ? "soft" : "ghost"}
        color={active ? undefined : "gray"}
        highContrast={active}
        style={{ justifyContent: "flex-start", width: "100%", borderRadius: "10px" }}
      >
        <Flex align="center" gap="2">
          {icon}
          <span>{label}</span>
        </Flex>
      </Button>
    </Link>
  );
}

function ExternalLinkButton({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{ textDecoration: "none" }}
    >
      <Button
        variant="ghost"
        style={{ justifyContent: "flex-start", width: "100%" }}
      >
        <Flex align="center" gap="2">
          <Text>{label}</Text>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </Flex>
      </Button>
    </a>
  );
}
