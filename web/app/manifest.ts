import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "رزق · رادار السيولة والزخم",
    short_name: "رزق",
    description: "إشارات دخول وخروج من صافي تدفق الأموال مع أسعار مقترحة وهدف ووقف خسارة",
    start_url: "/?v=5",
    display: "standalone",
    background_color: "#0B0F19",
    theme_color: "#0B0F19",
    lang: "ar",
    dir: "rtl",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
