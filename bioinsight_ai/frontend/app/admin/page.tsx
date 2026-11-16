// frontend/app/admin/page.tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Button from "@/components/Button";

type User = {
  email: string;
  fullName: string;
  organization: string;
  jobTitle: string;
  additionalInfo: string;
};

type DynamoUserItem = {
  user_email: { S: string };
  full_name: { S: string };
  organization: { S: string };
  job_title: { S: string };
  additional_info?: { S: string };
};

type AdminVerifyResponse = {
  status: string;
  sub?: string;
  role?: string;
  full_name?: string;
};

export default function Admin() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [adminEmail, setAdminEmail] = useState<string>("");
  const [loadingList, setLoadingList] = useState(true);
  const [approvingEmail, setApprovingEmail] = useState<string | null>(null);
  const [selectedEnvs, setSelectedEnvs] = useState<Record<string, string[]>>({});

  const ENVIRONMENTS = ["prod", "stage", "dev"] as const;

  function toggleEnv(email: string, env: string) {
    setSelectedEnvs((prev) => {
      const current = prev[email] || ["prod"];
      const updated = current.includes(env)
        ? current.filter((e) => e !== env)
        : [...current, env];
      // Ensure at least one environment is selected
      return { ...prev, [email]: updated.length > 0 ? updated : current };
    });
  }

  // ✅ Validate cookie & role on load
  useEffect(() => {
    async function validateAndLoad() {
      try {
        const res = await fetch(`/api/admin/verify`, {
          method: "GET",
          credentials: "include",
        });

        if (!res.ok) {
          router.push("/login");
          return;
        }

        const data: AdminVerifyResponse = await res.json();
        if (data.role !== "admin") {
          router.push("/chat"); // ✅ non-admins go to chat
          return;
        }

        setAdminEmail(data.full_name || data.sub || "");
        await fetchUsers(); // load pending users immediately
      } catch {
        router.push("/login");
      }
    }

    validateAndLoad();
  }, [router]);

  const fetchUsers = useCallback(async () => {
    setLoadingList(true);
    setError("");

    try {
      const res = await fetch(`/api/admin/pending-users`, {
        method: "GET",
        credentials: "include",
      });

      if (res.status === 401 || res.status === 403) {
        router.push("/login");
        return;
      }

      if (res.ok) {
        const data = await res.json();
        const pending: User[] = (data.users as DynamoUserItem[]).map((u) => ({
          email: u.user_email.S,
          fullName: u.full_name.S,
          organization: u.organization.S,
          jobTitle: u.job_title.S,
          additionalInfo: u.additional_info?.S || "",
        }));
        setUsers(pending);
      } else {
        setError("Failed to load pending users.");
      }
    } catch {
      setError("Error loading users.");
    } finally {
      setLoadingList(false);
    }
  }, [router]);

  async function approve(email: string) {
    setApprovingEmail(email);
    setError("");

    const envs = selectedEnvs[email] || ["prod"];

    try {
      const res = await fetch(`/api/admin/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          email,
          allowed_environments: envs.join(","),
        }),
        credentials: "include",
      });

      if (res.status === 401 || res.status === 403) {
        router.push("/login");
        return;
      }

      if (res.ok) {
        setUsers((prev) => prev.filter((u) => u.email !== email));
        await fetchUsers(); // ✅ refresh list after approval
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "Approval failed.");
      }
    } catch {
      setError("Approval request failed.");
    } finally {
      setApprovingEmail(null);
    }
  }

  async function deny(email: string) {
    setApprovingEmail(email);
    setError("");

    try {
      const res = await fetch(`/api/admin/deny`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ email }),
        credentials: "include",
      });

      if (res.status === 401 || res.status === 403) {
        router.push("/login");
        return;
      }

      if (res.ok) {
        // Remove denied user from local list
        setUsers((prev) => prev.filter((u) => u.email !== email));
        await fetchUsers();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "Denial failed.");
      }
    } catch {
      setError("Denial request failed.");
    } finally {
      setApprovingEmail(null);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left column: admin panel */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-start bg-gray-50 dark:bg-gray-900 p-10 overflow-y-auto">
        <div className="w-full max-w-2xl bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg">
          {/* Header */}
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Pending Users
              </h1>
              {adminEmail && (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Signed in as <span className="font-medium">{adminEmail}</span>
                </p>
              )}
            </div>
            <div className="flex items-center gap-4">
              <Link
                href="/chat/"
                className="text-pink-600 hover:underline text-sm"
              >
                Back to Chat
              </Link>
              <Button
                onClick={fetchUsers}
                variant="secondary"
                fullWidth={false}
              >
                Refresh
              </Button>
            </div>
          </div>

          {/* Errors */}
          {error && (
            <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-200">
              {error}
            </p>
          )}

          {/* List */}
          {loadingList ? (
            <p className="text-gray-700 dark:text-gray-300">Loading…</p>
          ) : users.length === 0 ? (
            <p className="text-gray-700 dark:text-gray-300">
              No pending users.
            </p>
          ) : (
            <div className="space-y-3">
              {users.map((u) => (
                <div
                  key={u.email}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 p-4"
                >
                  <p className="font-medium text-gray-900 dark:text-gray-100">
                    {u.fullName}{" "}
                    <span className="text-gray-600 dark:text-gray-400">
                      ({u.email})
                    </span>
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {u.jobTitle} @ {u.organization}
                  </p>
                  {u.additionalInfo && (
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      Note: {u.additionalInfo}
                    </p>
                  )}
                  <div className="mt-3">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Environment Access:
                    </p>
                    <div className="flex gap-4">
                      {ENVIRONMENTS.map((env) => (
                        <label
                          key={env}
                          className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={(selectedEnvs[u.email] || ["prod"]).includes(env)}
                            onChange={() => toggleEnv(u.email, env)}
                            className="rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                          />
                          {env}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="mt-3 flex gap-3">
                    <Button
                      onClick={() => approve(u.email)}
                      loading={approvingEmail === u.email}
                      fullWidth={false}
                    >
                      Approve
                    </Button>
                    <Button
                      onClick={() => deny(u.email)}
                      variant="secondary"
                      loading={approvingEmail === u.email}
                      fullWidth={false}
                    >
                      Deny
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right column: branding */}
      <div className="hidden lg:flex w-1/2 items-center justify-center bg-white dark:bg-gray-800">
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
  );
}
