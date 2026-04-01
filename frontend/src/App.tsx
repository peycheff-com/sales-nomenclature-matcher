import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { ErrorBoundary } from "@/components/error-boundary";
import { router } from "@/router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

/** GAP-9.8: Offline/online detection */
function useOnlineStatus() {
  useEffect(() => {
    let offlineToastId: string | number | undefined;

    const handleOffline = () => {
      offlineToastId = toast.error("Нет подключения к интернету", {
        duration: Infinity,
        id: "offline-status",
      });
    };
    const handleOnline = () => {
      toast.dismiss(offlineToastId);
      toast.success("Подключение восстановлено", { duration: 3000 });
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, []);
}

export default function App() {
  useOnlineStatus();

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster position="top-right" richColors closeButton />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
