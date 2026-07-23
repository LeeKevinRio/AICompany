import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
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
          <div className="flex-1">{children}</div>
          <footer className="border-t border-neutral-800 px-4 py-3 text-center text-sm text-neutral-400">
            本工具為研究與教育用途，非投資建議
          </footer>
        </Providers>
      </body>
    </html>
  );
}
