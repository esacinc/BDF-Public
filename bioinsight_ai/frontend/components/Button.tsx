// frontend/components/Button.tsx
import React from "react";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  children: React.ReactNode;
  variant?: "primary" | "secondary";
  fullWidth?: boolean;
  loading?: boolean; 
};

export default function Button({
  children,
  variant = "primary",
  fullWidth = true,
  loading = false,
  disabled,
  className = "",
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center rounded-md px-4 py-3 text-sm font-medium transition " +
    "focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed";

  const styles =
    variant === "secondary"
      ? "bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-400 " +
        "dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600"
      : "bg-pink-600 text-white hover:bg-pink-700 focus:ring-pink-500";

  const width = fullWidth ? "w-full" : "";
  const merged = [base, styles, width, className].filter(Boolean).join(" ");

  return (
    <button
      className={merged}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && (
        <svg
          className="mr-2 h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
            fill="none"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
      )}
      {children}
    </button>
  );
}
