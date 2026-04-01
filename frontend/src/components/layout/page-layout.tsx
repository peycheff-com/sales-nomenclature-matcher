import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface PageLayoutProps {
  children: ReactNode;
  header?: ReactNode;
  className?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
}

export function PageLayout({ children, header, className = "", title, description, actions }: PageLayoutProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -5 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`container py-8 max-w-7xl mx-auto space-y-6 ${className}`}
    >
      {(title || description || actions) && (
        <div className="flex flex-col md:flex-row flex-wrap items-baseline justify-between gap-4">
          <div className="space-y-1">
            {title && <h1 className="text-3xl font-bold tracking-tight">{title}</h1>}
            {description && <p className="text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {header && <div className="mb-6">{header}</div>}
      {children}
    </motion.div>
  );
}
