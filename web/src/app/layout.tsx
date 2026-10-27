import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { CrumbsProvider } from "@/lib/crumbs";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { THEME_BOOT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "ANT-OS Ω",
  description: "AFRICA-OS Ω decision intelligence: briefing, review queue, decisions, evidence and verified records.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <SessionProvider>
          <CrumbsProvider>
            <ToastProvider>
              <Suspense fallback={null}>
                <Shell>{children}</Shell>
              </Suspense>
            </ToastProvider>
          </CrumbsProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
