import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Cairo } from "next/font/google";

import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "رزق · رادار السيولة والزخم",
  description: "إشارات دخول وخروج من صافي تدفق الأموال مع أسعار مقترحة وهدف ووقف خسارة",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className={`${cairo.className} min-h-screen antialiased`}>{children}</body>
    </html>
  );
}
