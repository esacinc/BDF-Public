"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import Button from "@/components/Button";
import FormField from "@/components/FormField";
import { useRouter } from "next/navigation";

type SignupForm = {
  full_name: string;
  email: string;
  organization: string;
  job_title: string;
  additional_info?: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

export default function SignupClient() {
  const router = useRouter();
  const [form, setForm] = useState<SignupForm>({
    full_name: "",
    email: "",
    organization: "",
    job_title: "",
    additional_info: "",
  });
  const [message, setMessage] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const [touched, setTouched] = useState<Record<string, boolean>>({});

  useEffect(() => {
    localStorage.removeItem("token");
  }, []);

  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email);
  const fullNameOk = !!form.full_name.trim();
  const orgOk = !!form.organization.trim();
  const jobTitleOk = !!form.job_title.trim();

  const canSubmit = useMemo(
    () => fullNameOk && orgOk && jobTitleOk && emailOk && !loading,
    [fullNameOk, orgOk, jobTitleOk, emailOk, loading]
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setMessage("");
    setLoading(true);

    try {
      const normalizedEmail = form.email.trim().toLowerCase();

      const res = await fetch(`${API_BASE}/api/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          full_name: form.full_name,
          email: normalizedEmail,
          organization: form.organization,
          job_title: form.job_title,
          additional_info: form.additional_info || "",
        }),
        redirect: "manual",
      });

      if (res.type === "opaqueredirect" || res.status === 303) {
        window.location.href = `${API_BASE}/login?error=An account with ${encodeURIComponent(
          normalizedEmail
        )} already exists. Please log in instead.`;
        return;
      }

      if (res.ok) {
        router.push(`/auth/pending?email=${encodeURIComponent(normalizedEmail)}`);
      } else {
        const data = await res.json().catch(() => ({}));
        setMessage(data.detail || "❌ Signup failed.");
      }
    } catch (err) {
      console.error("Signup error:", err);
      setMessage("❌ Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left column */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 p-10">
        <div className="w-full max-w-md bg-white dark:bg-gray-800 p-10 rounded-xl shadow-lg">
          <h2 className="text-2xl font-bold text-center mb-2 text-gray-900 dark:text-gray-100">
            Sign Up
          </h2>
          <p className="text-center text-sm mb-6 text-gray-600 dark:text-gray-400">
            Fields marked with <span className="text-red-500">*</span> are required.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <FormField
              id="full_name"
              label="Full Name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              onBlur={() => setTouched({ ...touched, full_name: true })}
              placeholder="Jane Doe"
              required
              error={
                touched.full_name && !fullNameOk
                  ? "Full name is required."
                  : undefined
              }
              success={touched.full_name && fullNameOk}
            />

            <FormField
              id="email"
              label="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              onBlur={() => setTouched({ ...touched, email: true })}
              placeholder="jane.doe@example.com"
              required
              error={
                touched.email && !emailOk
                  ? "Please enter a valid email address."
                  : undefined
              }
              success={touched.email && emailOk}
            />

            <FormField
              id="organization"
              label="Organization"
              value={form.organization}
              onChange={(e) => setForm({ ...form, organization: e.target.value })}
              onBlur={() => setTouched({ ...touched, organization: true })}
              placeholder="Organization"
              required
              error={
                touched.organization && !orgOk
                  ? "Organization is required."
                  : undefined
              }
              success={touched.organization && orgOk}
            />

            <FormField
              id="job_title"
              label="Job Title"
              value={form.job_title}
              onChange={(e) => setForm({ ...form, job_title: e.target.value })}
              onBlur={() => setTouched({ ...touched, job_title: true })}
              placeholder="Research Scientist"
              required
              error={
                touched.job_title && !jobTitleOk
                  ? "Job title is required."
                  : undefined
              }
              success={touched.job_title && jobTitleOk}
            />

            <FormField
              id="additional_info"
              label="Additional Information (optional)"
              value={form.additional_info || ""}
              onChange={(e) => setForm({ ...form, additional_info: e.target.value })}
              placeholder="Tell us anything else you'd like..."
              textarea
            />

            <Button type="submit" disabled={!canSubmit} loading={loading}>
              Sign Up
            </Button>
          </form>

          {message && (
            <p className="mt-4 text-sm text-gray-700 dark:text-gray-300" aria-live="polite">
              {message}
            </p>
          )}

          <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{" "}
            <Link href="/login" className="text-pink-600 hover:underline">
              Login
            </Link>
          </p>
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
