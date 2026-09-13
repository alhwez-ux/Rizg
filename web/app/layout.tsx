import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Cairo } from "next/font/google";

import { AppUpdateGuard } from "@/components/AppUpdateGuard";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "رزق · رادار السيولة والزخم",
  description: "إشارات دخول وخروج من صافي تدفق الأموال مع أسعار مقترحة وهدف ووقف خسارة",
  applicationName: "رزق",
  appleWebApp: {
    capable: true,
    title: "رزق",
    statusBarStyle: "black-translucent",
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
  colorScheme: "dark",
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className={`${cairo.className} min-h-screen antialiased`}>
        <script
          dangerouslySetInnerHTML={{
            __html: `(() => {var b="7";var k="rizg-build";try{var p=localStorage.getItem(k);if(p===b)return;var go=function(){try{localStorage.setItem(k,b);}catch(e){}if(p&&p!==b){var u=new URL(location.href);u.searchParams.set("v",b);location.replace(u.pathname+u.search);}};var jobs=[];if("serviceWorker"in navigator){jobs.push(navigator.serviceWorker.getRegistrations().then(function(rs){return Promise.all(rs.map(function(r){return r.unregister();}));}));}if(window.caches){jobs.push(caches.keys().then(function(ks){return Promise.all(ks.map(function(x){return caches.delete(x);}));}));}Promise.all(jobs).then(go).catch(go);}catch(e){}})();`,
          }}
        />
        <AppUpdateGuard />
        {children}
      </body>
    </html>
  );
}
