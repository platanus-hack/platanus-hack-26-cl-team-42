import { Outlet, createRootRoute } from "@tanstack/react-router";
import { AllAuthProvider } from "../services/auth";
import { StrictMode } from "react";
import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export const Route = createRootRoute({
  component: RootComponent,
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function RootComponent() {
  return (
    <StrictMode>
      <Theme appearance="light" accentColor="teal" grayColor="slate" radius="large" scaling="100%">
        <QueryClientProvider client={queryClient}>
          <AllAuthProvider>
            <Outlet />
          </AllAuthProvider>
        </QueryClientProvider>
      </Theme>
    </StrictMode>
  );
}
