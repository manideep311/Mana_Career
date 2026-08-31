"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  ToastClose,
  ToastDescription,
  ToastRoot,
  ToastTitle,
  type ToastVariant,
} from "@/components/ui/toast";

type ToastOptions = {
  title: string;
  description?: string;
  variant?: ToastVariant;
};

type QueuedToast = ToastOptions & { id: number };

type ToastContextValue = {
  toast: (t: ToastOptions) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <Toaster>");
  }
  return ctx;
}

export function Toaster({ children }: { children?: ReactNode }) {
  const [toasts, setToasts] = useState<QueuedToast[]>([]);
  const idRef = useRef(0);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((t: ToastOptions) => {
    idRef.current += 1;
    setToasts((prev) => [...prev, { ...t, id: idRef.current }]);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ toast }), [toast]);

  return (
    <ToastPrimitive.Provider>
      <ToastContext.Provider value={value}>
        {children}
        {toasts.map(({ id, title, description, variant }) => (
          <ToastRoot
            key={id}
            variant={variant}
            onOpenChange={(open) => {
              if (!open) remove(id);
            }}
          >
            <div className="flex-1">
              <ToastTitle>{title}</ToastTitle>
              {description ? (
                <ToastDescription>{description}</ToastDescription>
              ) : null}
            </div>
            <ToastClose aria-label="Dismiss notification">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="h-4 w-4"
                aria-hidden="true"
              >
                <path
                  d="m6 6 12 12M18 6 6 18"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </ToastClose>
          </ToastRoot>
        ))}
        <ToastPrimitive.Viewport
          aria-live="polite"
          className="fixed bottom-0 left-0 right-0 z-[100] flex max-h-screen flex-col gap-2 p-4 outline-none md:left-auto md:w-96"
        />
      </ToastContext.Provider>
    </ToastPrimitive.Provider>
  );
}

export { Toaster as ToastProvider };
