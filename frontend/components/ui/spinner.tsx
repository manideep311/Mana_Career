import { cn } from "@/lib/cn";

type SpinnerProps = {
  size?: "sm" | "md";
  className?: string;
};

export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <svg
      role="status"
      aria-label="Loading"
      viewBox="0 0 24 24"
      fill="none"
      className={cn(
        "animate-spin motion-reduce:animate-none",
        size === "sm" ? "h-4 w-4" : "h-5 w-5",
        className,
      )}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
