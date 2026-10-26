import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import { NavBar } from "./components/NavBar";
import { SITE_FOOTER_DISCLAIMER } from "./lib/riskRemediationWording";
import "./globals.css";

export const metadata: Metadata = {
  title: "stock-desk",
  description: "股票訊號分析與部位決策輔助工具",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-Hant" className="dark">
      <body className="min-h-screen flex flex-col bg-black text-neutral-100">
        <Providers>
          <NavBar />
          <div className="flex-1">{children}</div>
          {/* Risk remediation 3-F (C-8): site-wide disclaimer, never weaker than text-sm / neutral-400, never folded. 風控 2026-10-26 定稿；失效條件 T2、T7、T8. */}
          <footer className="border-t border-neutral-800 px-4 py-3 text-center text-sm text-neutral-400">
            <p className="mx-auto max-w-3xl">{SITE_FOOTER_DISCLAIMER}</p>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
