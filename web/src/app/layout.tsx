import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Suspense, type ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { CrumbsProvider } from "@/lib/crumbs";
import { SessionProvider } from "@/lib/session";
import { THEME_BOOT } from "@/lib/theme";
import { ToastProvider } from "@/lib/toast";

import "./globals.css";

// Self-hosted at build time by next/font: no request to Google from visitors.
const sans = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "ANT-OS Ω",
  description: "AFRICA-OS Ω decision intelligence: briefing, review queue, decisions, evidence and verified records.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
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
