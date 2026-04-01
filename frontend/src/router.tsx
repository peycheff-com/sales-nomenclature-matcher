import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
  Outlet,
} from "@tanstack/react-router";
import {
  isAuthenticated,
  setAuthenticated,
  mustChangePassword,
  setMustChangePassword,
} from "@/lib/auth-store";
import { getMe } from "@/api/auth";
import { queryClient } from "@/lib/query-client";
import AppShell from "@/components/layout/app-shell";
import LoginPage from "@/pages/login";
import DashboardPage from "@/pages/dashboard";
import ResultsPage from "@/pages/results";
import CatalogPage from "@/pages/catalog";
import SettingsPage from "@/pages/settings";
import ProfilePage from "@/pages/profile";
import ForceChangePasswordPage from "@/pages/force-change-password";
import { NotFound } from "@/pages/not-found";

/**
 * Check if user is authenticated and whether they must change password.
 *
 * Since auth state is in-memory, a page refresh loses it.
 * On first protected route load, we probe /auth/me (cookie is sent
 * automatically). If it succeeds, restore the in-memory flags.
 */
async function ensureAuthenticated(): Promise<{
  authed: boolean;
  mustChange: boolean;
}> {
  if (isAuthenticated()) {
    return { authed: true, mustChange: mustChangePassword() };
  }
  try {
    const user = await queryClient.ensureQueryData({
      queryKey: ["me"],
      queryFn: getMe,
      staleTime: 5 * 60 * 1000,
    });
    setAuthenticated(true);
    setMustChangePassword(user.must_change_password);
    return { authed: true, mustChange: user.must_change_password };
  } catch {
    return { authed: false, mustChange: false };
  }
}



// Root route -- just renders outlet
const rootRoute = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: NotFound,
});

// Public: login
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
  beforeLoad: async () => {
    const { authed, mustChange } = await ensureAuthenticated();
    if (authed) {
      throw redirect({ to: mustChange ? "/change-password" : "/" });
    }
  },
});

// Force change password (requires auth, but outside AppShell)
const forceChangePasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/change-password",
  component: ForceChangePasswordPage,
  beforeLoad: async () => {
    const { authed, mustChange } = await ensureAuthenticated();
    if (!authed) throw redirect({ to: "/login" });
    if (!mustChange) throw redirect({ to: "/" });
  },
});

// Auth layout route -- checks auth, renders AppShell with Outlet
const authLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  component: AppShell,
  beforeLoad: async () => {
    const { authed, mustChange } = await ensureAuthenticated();
    if (!authed) throw redirect({ to: "/login" });
    if (mustChange) throw redirect({ to: "/change-password" });
  },
});

// Dashboard (index)
const dashboardRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/",
  component: DashboardPage,
});


// Results for a specific request
const resultsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/requests/$requestId",
  component: ResultsPage,
});


// Catalog
const catalogRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/catalog",
  component: CatalogPage,
});


// Settings (requires admin role)
const settingsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/settings",
  component: SettingsPage,
  beforeLoad: async () => {
    try {
      const user = await queryClient.ensureQueryData({
        queryKey: ["me"],
        queryFn: getMe,
        staleTime: 5 * 60 * 1000,
      });
      if (user.role !== "admin") {
        throw redirect({ to: "/" });
      }
    } catch (e) {
      if (e instanceof Error) throw redirect({ to: "/" });
      throw e; // re-throw redirect
    }
  },
});


// User profile (any authenticated user)
const profileRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/profile",
  component: ProfilePage,
});

// Build the route tree
const routeTree = rootRoute.addChildren([
  loginRoute,
  forceChangePasswordRoute,
  authLayoutRoute.addChildren([
    dashboardRoute,
    resultsRoute,
    catalogRoute,
    settingsRoute,
    profileRoute,
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
