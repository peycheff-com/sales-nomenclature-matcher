import { useEffect, useRef } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { ErrorBoundary } from "@/components/error-boundary";
import { queryClient } from "@/lib/query-client";
import { router } from "@/router";

/** GAP-9.8: Offline/online detection (debounced to avoid flicker) */
function useOnlineStatus() {
  const offlineTimerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let offlineToastId: string | number | undefined;

    const handleOffline = () => {
      clearTimeout(offlineTimerRef.current);
      offlineTimerRef.current = setTimeout(() => {
        offlineToastId = toast.error("Нет подключения к интернету", {
          duration: Infinity,
          id: "offline-status",
        });
      }, 1000);
    };
    const handleOnline = () => {
      clearTimeout(offlineTimerRef.current);
      toast.dismiss(offlineToastId);
      toast.success("Подключение восстановлено", { duration: 3000 });
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      clearTimeout(offlineTimerRef.current);
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
