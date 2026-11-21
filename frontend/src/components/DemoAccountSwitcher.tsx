import { useMutation, useQuery } from "@tanstack/react-query";
import { Badge, Button, Flex, Separator, Text } from "@radix-ui/themes";
import { apiRequest } from "../services/api/client";
import { professionLabel } from "../modules/recordings/professions";

interface DemoAccount {
  email: string;
  name: string;
  profession: string;
  current: boolean;
}

/** Solo en desarrollo: cambia de cuenta de demo sin cerrar sesión (para probar flujos entre profesionales). */
export function DemoAccountSwitcher() {
  const { data: accounts = [] } = useQuery({
    queryKey: ["dev-accounts"],
    queryFn: () => apiRequest<DemoAccount[]>("/dev/accounts"),
    retry: false,
  });
  const switchTo = useMutation({
    mutationFn: (email: string) =>
      apiRequest<DemoAccount>("/dev/switch", { method: "POST", body: JSON.stringify({ email }) }),
    // La sesión cambió: se recarga la página para que todo se vuelva a pedir como la otra cuenta.
    onSuccess: () => window.location.reload(),
  });

  if (accounts.length === 0) return null;
  return (
    <>
      <Text size="1" color="gray" weight="medium">
        Cambiar de usuario (demo)
      </Text>
      <Flex direction="column" gap="1">
        {accounts.map((account) => (
          <Button
            key={account.email}
            variant={account.current ? "soft" : "ghost"}
            color={account.current ? undefined : "gray"}
            disabled={account.current}
            loading={switchTo.isPending && switchTo.variables === account.email}
            onClick={() => switchTo.mutate(account.email)}
            style={{ justifyContent: "space-between", height: "auto", padding: "6px 8px" }}
          >
            <Flex direction="column" align="start">
              <span>{account.name || account.email.split("@")[0]}</span>
              <Text size="1" color="gray">
                {account.profession ? professionLabel(account.profession) : "Sin profesión definida"}
              </Text>
            </Flex>
            {account.current && (
              <Badge size="1" variant="soft">
                Actual
              </Badge>
            )}
          </Button>
        ))}
      </Flex>
      <Separator size="4" />
    </>
  );
}
