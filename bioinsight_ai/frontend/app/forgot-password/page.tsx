// frontend/app/reset-password/page.tsx
"use client";

import { useState, useMemo } from "react";
import Button from "@/components/Button";
import FormField from "@/components/FormField";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const emailOk = useMemo(() => /\S+@\S+\.\S+/.test(email), [email]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!emailOk) return;
    setMessage("");
    setLoading(true);

    try {
      const normalizedEmail = email.trim().toLowerCase();

      const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ email: normalizedEmail }),
      });

      if (res.ok) {
        setMessage("✅ If your account is password-based, a reset email has been sent.");
      } else {
        const data = await res.json().catch(() => ({}));
        setMessage(data.detail || "❌ Unable to process request.");
      }
    } catch (err) {
      console.error("Forgot password error:", err);
      setMessage("❌ Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left column with form */}
      <div className="flex w-full lg:w-1/2 items-center justify-center bg-gray-50 dark:bg-gray-900 p-6">
        <div className="w-full max-w-md bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg">
          <h2 className="text-2xl font-bold mb-4 text-center">Forgot Password</h2>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <FormField
              id="email"
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="me@example.com"
              required
              autoComplete="email"
            />
            <Button type="submit" disabled={!emailOk || loading} loading={loading}>
              Send Reset Email
            </Button>
          </form>
          {message && (
            <p className="mt-4 text-sm text-gray-700 dark:text-gray-300">{message}</p>
          )}
        </div>
      </div>

      {/* Right column branding (optional) */}
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
