import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
  Outlet,
} from "@tanstack/react-router";
import { isAuthenticated, setAuthenticated } from "@/lib/auth-store";
import { getMe } from "@/api/auth";
import AppShell from "@/components/layout/app-shell";
import LoginPage from "@/pages/login";
import DashboardPage from "@/pages/dashboard";
import RequestsPage from "@/pages/requests";
import ResultsPage from "@/pages/results";
import AdminPage from "@/pages/admin";
import CatalogPage from "@/pages/catalog";
import SuppliersPage from "@/pages/suppliers";
import SettingsPage from "@/pages/settings";

/**
 * Check if user is authenticated.
 *
 * Since auth state is in-memory, a page refresh loses it.
 * On first protected route load, we probe /auth/me (cookie is sent
 * automatically). If it succeeds, restore the in-memory flag.
 */
async function ensureAuthenticated(): Promise<boolean> {
  if (isAuthenticated()) return true;
  try {
    await getMe();
    setAuthenticated(true);
    return true;
  } catch {
    return false;
  }
}

// Root route -- just renders outlet
const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

// Public: login
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
  beforeLoad: async () => {
    const authed = await ensureAuthenticated();
    if (authed) {
      throw redirect({ to: "/" });
    }
  },
});

// Auth layout route -- checks auth, renders AppShell with Outlet
const authLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  component: AppShell,
  beforeLoad: async () => {
    const authed = await ensureAuthenticated();
    if (!authed) {
      throw redirect({ to: "/login" });
    }
  },
});

// Dashboard (index)
const dashboardRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/",
  component: DashboardPage,
});

// Requests list
const requestsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/requests",
  component: RequestsPage,
});

// Results for a specific request
const resultsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/requests/$requestId",
  component: ResultsPage,
});

// Admin
const adminRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin",
  component: AdminPage,
});

// Catalog
const catalogRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/catalog",
  component: CatalogPage,
});

// Suppliers
const suppliersRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/suppliers",
  component: SuppliersPage,
});

// Settings
const settingsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/settings",
  component: SettingsPage,
});

// Build the route tree
const routeTree = rootRoute.addChildren([
  loginRoute,
  authLayoutRoute.addChildren([
    dashboardRoute,
    requestsRoute,
    resultsRoute,
    adminRoute,
    catalogRoute,
    suppliersRoute,
    settingsRoute,
  ]),
]);

// Create and export the router
export const router = createRouter({ routeTree });

// Type registration for TanStack Router
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
