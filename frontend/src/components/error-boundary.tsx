import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center p-4">
          <div className="text-center space-y-4 max-w-lg">
            <div className="mx-auto w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
              <span className="text-red-600 text-xl">!</span>
            </div>
            <h1 className="text-2xl font-bold">
              Произошла ошибка
            </h1>
            <p className="text-muted-foreground">
              Приложение столкнулось с непредвиденной ошибкой. Попробуйте обновить страницу.
            </p>
            {this.state.error?.message && (
              <details className="text-left rounded-lg border border-border bg-muted/30 p-3">
                <summary className="text-xs text-muted-foreground cursor-pointer select-none">
                  Техническая информация
                </summary>
                <pre className="mt-2 text-xs font-mono text-red-700 whitespace-pre-wrap break-words">
                  {this.state.error.message}
                </pre>
              </details>
            )}
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                }}
              >
                Попробовать снова
              </Button>
              <Button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.href = "/";
                }}
              >
                На главную
              </Button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
