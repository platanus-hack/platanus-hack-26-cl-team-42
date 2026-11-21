import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";
import { useAuth } from "../../services/auth";

interface AccountProfile {
  name: string;
  email: string;
  profession: string;
  admin_url: string | null;
}

export function useAccountProfile() {
  const { session } = useAuth();

  return useQuery({
    queryKey: ["account-profile", session.id],
    queryFn: () => apiRequest<AccountProfile>("/users/me"),
    enabled: session.authenticated,
  });
}

export function accountTypeLabel(profile: AccountProfile) {
  return profile.admin_url ? "Cuenta administrativa" : "Cuenta estándar";
}
