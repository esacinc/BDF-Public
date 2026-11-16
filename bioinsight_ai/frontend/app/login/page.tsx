// frontend/app/login/page.tsx
"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Button from "@/components/Button";
import FormField from "@/components/FormField";

export default function Login() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [fullName, setFullName] = useState("");

  // ✅ Handle ?error / ?success messages
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const err = params.get("error");
      const ok = params.get("success");
      if (err) setError(err);
      if (ok) setSuccess(ok);

      // Clean up URL params after showing message
      if (err || ok) {
        window.history.replaceState({}, "", "/login");
      }
    }
  }, []);

  // ✅ Verify cookie session on mount
  useEffect(() => {
    async function verify() {
      try {
        const res = await fetch("/api/auth/verify", {
          method: "GET",
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setLoggedIn(true);
          setFullName(data.full_name || data.sub || "");
        } else {
          setLoggedIn(false);
          setFullName("");
        }
      } catch {
        setLoggedIn(false);
        setFullName("");
      }
    }
    verify();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError("");
    setSuccess("");
    setSubmitting(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          identifier: identifier.trim().toLowerCase(),
          password,
        }),
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json().catch(() => ({}));

        if (data.force_change_pw) {
          localStorage.setItem("identifier", identifier.trim().toLowerCase());
          window.location.href = "/change-password";
          return;
        }

        if (data.access_token) {
          if (data.full_name) setFullName(data.full_name);
          window.location.href = "/chat/?login=" + Date.now();
          return;
        }

        setError("No token returned from server");
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "Login failed");
      }
    } catch (err) {
      console.error("Login error:", err);
      setError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      await fetch("/chat/reset-session", {
        method: "GET",
        credentials: "include",
      }).catch(() => {});
    } catch (err) {
      console.error("Logout failed:", err);
    }
    setLoggedIn(false);
    setFullName("");
    window.location.replace("/login");
  }

  function handleGoogleLogin() {
    window.location.href = "/api/auth/google/login";
  }

  return (
    <div className="flex min-h-screen">
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 p-10">
        <div className="h-40 flex items-center justify-center mb-6">
          <img
            src="/logo_light.png"
            alt="BioInsight Small Logo"
            className="h-36 w-auto dark:hidden"
          />
          <img
            src="/logo_dark.png"
            alt="BioInsight Small Logo"
            className="h-36 w-auto hidden dark:block"
          />
        </div>

        <div className="w-full max-w-md bg-white dark:bg-gray-800 p-10 rounded-xl shadow-lg">
          {!loggedIn ? (
            <>
              <h2 className="text-2xl font-bold text-center mb-6 text-gray-900 dark:text-gray-100">
                Login to access the app
              </h2>

              {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
              {success && <p className="text-green-600 text-sm mb-4">{success}</p>}

              <form onSubmit={handleSubmit} className="space-y-4">
                <FormField
                  id="identifier"
                  label="Username or Email"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="me@example.com"
                  required
                  autoComplete="username"
                />

                <FormField
                  id="password"
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                />

                <Button
                  type="submit"
                  loading={submitting}
                  disabled={submitting}
                  className="w-full bg-pink-600 hover:bg-pink-700 text-white"
                >
                  Sign In
                </Button>
              </form>

              <div className="mt-4 text-right">
                <Link
                  href="/forgot-password"
                  className="text-sm text-pink-600 hover:underline"
                >
                  Forgot password?
                </Link>
              </div>

              <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
                Don’t have an account?{" "}
                <Link href="/auth" className="text-pink-600 hover:underline">
                  Sign Up
                </Link>
              </p>

              <div className="flex items-center my-6">
                <hr className="flex-grow border-gray-300 dark:border-gray-600" />
                <span className="mx-4 text-gray-500">OR</span>
                <hr className="flex-grow border-gray-300 dark:border-gray-600" />
              </div>

              <button
                type="button"
                onClick={handleGoogleLogin}
                className="w-full h-12 flex items-center justify-center border border-gray-300 rounded-md shadow-sm bg-white text-gray-700 hover:bg-gray-50 font-medium text-sm"
                style={{ fontFamily: "Roboto, sans-serif" }}
              >
                <div className="flex items-center">
                  <div className="bg-white p-1 rounded-full mr-3">
                    <img
                      src="https://www.svgrepo.com/show/355037/google.svg"
                      alt="Google"
                      className="h-5 w-5"
                    />
                  </div>
                  Sign in with Google
                </div>
              </button>
            </>
          ) : (
            <>
              <h2 className="text-2xl font-bold text-center mb-6 text-gray-900 dark:text-gray-100">
                Welcome, {fullName || "User"} 🎉
              </h2>
              <Button onClick={handleLogout}>Logout</Button>
            </>
          )}
        </div>
      </div>

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
