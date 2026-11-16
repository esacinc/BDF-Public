// components/FormField.tsx
import React from "react";

type FormFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  onBlur?: (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  placeholder?: string;
  required?: boolean;
  type?: string;
  textarea?: boolean;
  error?: string;
  success?: boolean;
  // ✅ extra passthrough props
  autoComplete?: string;
  minLength?: number;
  maxLength?: number;
};

export default function FormField({
  id,
  label,
  value,
  onChange,
  onBlur,
  onFocus,
  placeholder,
  required = false,
  type = "text",
  textarea = false,
  error,
  success,
  autoComplete,
  minLength,
  maxLength,
}: FormFieldProps) {
  const baseClasses =
    "mt-1 block w-full rounded-md px-4 py-3 text-sm shadow-sm transition-colors bg-gray-100 dark:bg-gray-700 dark:text-white placeholder-gray-400 focus:outline-none";

  const stateClasses = error
    ? "border border-red-500 focus:border-red-500 focus:ring-1 focus:ring-red-500"
    : success
    ? "border border-green-500 focus:border-green-500 focus:ring-1 focus:ring-green-500"
    : "border border-transparent focus:border-pink-500 focus:ring-1 focus:ring-pink-500";

  return (
    <div className="mb-5">
      <label
        htmlFor={id}
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
      >
        {label} {required && <span className="text-red-500">*</span>}
      </label>

      {textarea ? (
        <textarea
          id={id}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          onFocus={onFocus}
          placeholder={placeholder}
          required={required}
          autoComplete={autoComplete}
          minLength={minLength}
          maxLength={maxLength}
          className={`${baseClasses} ${stateClasses} min-h-[100px]`}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          onFocus={onFocus}
          placeholder={placeholder}
          required={required}
          autoComplete={autoComplete}
          minLength={minLength}
          maxLength={maxLength}
          className={`${baseClasses} ${stateClasses}`}
        />
      )}

      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
      {success && !error && (
        <p className="mt-1 text-xs text-green-600">✓ Looks good</p>
      )}
    </div>
  );
}
