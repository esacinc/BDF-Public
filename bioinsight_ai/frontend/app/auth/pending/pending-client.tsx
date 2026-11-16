// frontend/app/auth/pending/pending-client.tsx
"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";

export default function PendingCard() {
  const params = useSearchParams();
  const email = params.get("email") || "";

  return (
    <div
      className="w-full max-w-md bg-white dark:bg-gray-800 p-10 rounded-xl shadow-lg text-center"
      role="status"
    >
      <div className="flex justify-center mb-6">
        <CheckCircle2
          className="h-14 w-14 text-green-500"
          aria-hidden="true"
        />
      </div>

      <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
        Thank You!
      </h1>

      <p className="text-sm text-gray-700 dark:text-gray-300 mb-6 leading-relaxed">
        Your registration has been received and is pending admin approval.
        {email && (
          <>
            {" "}
            We’ll email you at{" "}
            <span className="font-bold">
              <code>{email}</code>
            </span>{" "}
            when your account is ready.
          </>
        )}
      </p>

      <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
        <p>
          Already approved?{" "}
          <Link href="/login" className="text-pink-600 hover:underline">
            Log in
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
