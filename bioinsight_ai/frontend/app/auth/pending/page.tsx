// frontend/app/auth/pending/page.tsx
import { Suspense } from "react";
import PendingCard from "./pending-client";

// ✅ Add page metadata (Next.js 13+)
export const metadata = {
  title: "Signup Pending | BioInsight AI",
  description: "Your BioInsight AI signup request is pending admin approval.",
};

// ✅ Force dynamic rendering to avoid prerender errors for search params
export const dynamic = "force-dynamic";

export default function SignupPendingPage() {
  return (
    <div className="flex min-h-screen">
      {/* Left column */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 p-10">
        <Suspense
          fallback={
            <div className="w-full max-w-md bg-white dark:bg-gray-800 p-10 rounded-xl shadow-lg text-center">
              <div className="h-6 w-40 mx-auto mb-4 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-64 mx-auto mb-2 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-56 mx-auto mb-6 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Loading your pending request…
              </p>
            </div>
          }
        >
          <PendingCard />
        </Suspense>
      </div>

      {/* Right column with your branding */}
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
