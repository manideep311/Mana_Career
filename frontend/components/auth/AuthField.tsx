"use client";

import { forwardRef, useState, type ComponentProps, type ReactNode } from "react";

import { Eye, EyeOff, Lock, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

type AuthFieldProps = Omit<ComponentProps<"input">, "id"> & {
  id: string;
  label: string;
  icon: LucideIcon;
  error?: string;
  hint?: string;
  /** Rendered at the right edge of the box (e.g. a show-password toggle). */
  trailing?: ReactNode;
};

/**
 * The account pages' text box: an icon, a small label inside the box above
 * the value, and the hint / error underneath, wired to `aria-describedby`.
 */
export const AuthField = forwardRef<HTMLInputElement, AuthFieldProps>(
  ({ id, label, icon: Icon, error, hint, trailing, className, ...props }, ref) => {
    const describedBy = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean);
    return (
      <div className="flex flex-col gap-1.5">
        <div
          className={cn(
            "flex items-center gap-3.5 rounded-2xl border bg-white px-4 py-2.5 shadow-[0_1px_2px_rgba(21,19,31,0.04)] transition-[border-color,box-shadow]",
            "focus-within:border-accent focus-within:ring-4 focus-within:ring-[var(--ring)]",
            error ? "border-danger" : "border-[#e3e0ef]",
          )}
        >
          <Icon className="h-5 w-5 shrink-0 text-text-muted" aria-hidden />
          <div className="flex min-w-0 flex-1 flex-col">
            <label htmlFor={id} className="text-xs font-medium text-text-muted">
              {label}
            </label>
            <input
              ref={ref}
              id={id}
              aria-invalid={error ? true : undefined}
              aria-describedby={describedBy.length ? describedBy.join(" ") : undefined}
              className={cn(
                "w-full bg-transparent text-[15px] text-text outline-none placeholder:text-text-muted/60",
                className,
              )}
              {...props}
            />
          </div>
          {trailing}
        </div>
        {hint ? (
          <p id={`${id}-hint`} className="px-1 text-xs text-text-muted">
            {hint}
          </p>
        ) : null}
        {error ? (
          <p id={`${id}-error`} role="alert" className="px-1 text-xs text-danger">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
AuthField.displayName = "AuthField";

/** A password box with a show / hide toggle. */
export const PasswordField = forwardRef<
  HTMLInputElement,
  Omit<AuthFieldProps, "icon" | "type" | "trailing">
>((props, ref) => {
  const [visible, setVisible] = useState(false);
  const Toggle = visible ? EyeOff : Eye;
  return (
    <AuthField
      ref={ref}
      icon={Lock}
      type={visible ? "text" : "password"}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-controls={props.id}
          className="-mr-1.5 rounded-lg p-1.5 text-text-muted transition hover:bg-surface-sunk hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <Toggle className="h-5 w-5" aria-hidden />
        </button>
      }
      {...props}
    />
  );
});
PasswordField.displayName = "PasswordField";
