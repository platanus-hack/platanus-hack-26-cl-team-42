import { createFileRoute, Navigate, Outlet } from "@tanstack/react-router";
import { AppHeader } from "../components/AppHeader";
import { BottomNav } from "../components/BottomNav";
import { useAuth } from "../services/auth";

export const Route = createFileRoute("/_authenticated")({
  component: AuthenticatedContent,
});

function AuthenticatedContent() {
  const { session, isConfigured } = useAuth();

  if (!isConfigured) {
    return <div>Loading...</div>;
  }

  if (!session.authenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <>
      <AppHeader userEmail={session?.email || ""} />
      <main className="app-main">
        <Outlet />
      </main>
      <BottomNav />
    </>
  );
}
