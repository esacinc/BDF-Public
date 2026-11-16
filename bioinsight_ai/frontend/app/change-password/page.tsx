"use client";

import { useState } from "react";
import Button from "@/components/Button";
import FormField from "@/components/FormField";
import { getPasswordStrength, getPasswordRules } from "@/utils/passwordUtils";

export default function ChangePassword() {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const strength = getPasswordStrength(newPassword);
  const rules = getPasswordRules(newPassword);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }

    if (!rules.every((r) => r.valid)) {
      setError("Password does not meet all requirements.");
      return;
    }

    let identifier = localStorage.getItem("identifier");
    if (!identifier) {
      setError("Missing user identifier. Please login again.");
      window.location.href = "/login";
      return;
    }
    identifier = identifier.trim().toLowerCase();

    setLoading(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          email: identifier,
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });

      if (res.ok) {
        setMessage("✅ Password changed. Please login again.");
        localStorage.removeItem("identifier");
        setOldPassword(""); // clear temp password
        setTimeout(() => (window.location.href = "/login"), 2000);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "❌ Failed to change password.");
      }
    } catch (err) {
      console.error("Change password error:", err);
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left column */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 p-10">
        <div className="w-full max-w-md bg-white dark:bg-gray-800 p-10 rounded-xl shadow-lg">
          <h2 className="text-2xl font-bold text-center mb-6 text-gray-900 dark:text-gray-100">
            Change Your Password
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <FormField
              id="old_password"
              label="Temporary Password"
              type="password"
              autoComplete="current-password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder="Enter your temporary password"
              required
            />

            <div>
              <FormField
                id="new_password"
                label="New Password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password"
                required
              />

              {newPassword && (
                <div className="mt-2 space-y-2">
                  {/* strength meter */}
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${strength.color}`}
                      style={{ width: `${(strength.score + 1) * 20}%` }}
                    ></div>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Strength:{" "}
                    <span
                      className={`font-medium ${strength.color.replace("bg-", "text-")}`}
                    >
                      {strength.label}
                    </span>
                  </p>

                  {/* rules checklist */}
                  <ul className="space-y-1 text-sm">
                    {rules.map((rule, idx) => (
                      <li
                        key={idx}
                        className={`flex items-center ${
                          rule.valid
                            ? "text-green-600"
                            : "text-gray-500 dark:text-gray-400"
                        }`}
                      >
                        {rule.valid ? "✓" : "✗"}{" "}
                        <span className="ml-2">{rule.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <FormField
              id="confirm_password"
              label="Confirm New Password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter new password"
              required
              error={
                confirmPassword && confirmPassword !== newPassword
                  ? "Passwords do not match"
                  : undefined
              }
            />

            {error && (
              <p className="text-red-500 text-sm" aria-live="polite">
                {error}
              </p>
            )}
            {message && (
              <p className="text-green-600 text-sm" aria-live="polite">
                {message}
              </p>
            )}

            <Button type="submit" disabled={loading} loading={loading}>
              Update Password
            </Button>
          </form>
        </div>
      </div>

      {/* Right column */}
      <div className="hidden lg:flex w-1/2 items-center justify-center bg-white dark:bg-gray-800">
        <div className="text-center">
          <img
            src="/logo_light.png"
            alt="BioInsight Logo"
            className="mx-auto h-[32rem] dark:hidden"
          />
          <img
            src="/logo_dark.png"
            alt="BioInsight Logo"
            className="mx-auto h-[32rem] hidden dark:block"
          />
        </div>
      </div>
    </div>
  );
}
