// frontend/utils/passwordUtils.ts
export type PasswordStrength = {
  score: number; // 0–4
  label: string;
  color: string;
};

export function getPasswordStrength(password: string): PasswordStrength {
  let score = 0;

  if (password.length >= 12) score++;
  if (password.length >= 16) score++;
  if (/[a-z]/.test(password)) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score++;

  score = Math.min(score, 4);

  const levels = [
    { label: "Weak", color: "bg-red-500" },
    { label: "Fair", color: "bg-yellow-500" },
    { label: "Good", color: "bg-blue-500" },
    { label: "Strong", color: "bg-green-500" },
    { label: "Very Strong", color: "bg-emerald-600" },
  ];

  return { score, ...levels[score] };
}

// ✅ password rule checks
export function getPasswordRules(password: string) {
  return [
    {
      label: "At least 12 characters",
      valid: password.length >= 12,
    },
    {
      label: "At least one lowercase letter",
      valid: /[a-z]/.test(password),
    },
    {
      label: "At least one uppercase letter",
      valid: /[A-Z]/.test(password),
    },
    {
      label: "At least one number",
      valid: /[0-9]/.test(password),
    },
    {
      label: "At least one special character",
      valid: /[!@#$%^&*(),.?\":{}|<>]/.test(password),
    },
  ];
}
