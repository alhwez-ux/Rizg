import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Cairo } from "next/font/google";

import { AppUpdateGuard } from "@/components/AppUpdateGuard";
import { ConnectionGuardProvider } from "@/hooks/useConnectionGuard";
import { CLIENT_BUILD } from "@/lib/auth/public-constants";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "رزق · رادار السيولة وفرص السوق",
  description: "إشارات دخول وخروج من صافي تدفق الأموال مع أسعار مقترحة وهدف ووقف خسارة",
  applicationName: "رزق",
  appleWebApp: {
    capable: true,
    title: "رزق",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/icons/icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    "msapplication-TileColor": "#0B0F19",
    "msapplication-TileImage": "/icons/icon-256.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#0B0F19",
  colorScheme: "dark light",
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ar" dir="rtl" data-theme="dark" suppressHydrationWarning>
      <body className={`${cairo.className} min-h-screen antialiased`}>
        <script
          dangerouslySetInnerHTML={{
            __html: THEME_BOOTSTRAP,
          }}
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `(() => {var b=${JSON.stringify(CLIENT_BUILD)};var k="rizg-build";try{var u=new URL(location.href);var q=u.searchParams.get("v");var p=localStorage.getItem(k);if(p===b&&q===b)return;var go=function(){try{localStorage.setItem(k,b);}catch(e){}u.searchParams.set("v",b);location.replace(u.pathname+u.search);};var jobs=[];if(window.caches){jobs.push(caches.keys().then(function(ks){return Promise.all(ks.map(function(x){return caches.delete(x);}));}));}Promise.all(jobs).then(go).catch(go);}catch(e){}})();`,
          }}
        />
        <ConnectionGuardProvider>
          <AppUpdateGuard />
          {children}
        </ConnectionGuardProvider>
      </body>
    </html>
  );
}
