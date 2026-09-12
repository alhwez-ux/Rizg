import type { Metadata } from "next";

import { StockRadarDemo } from "@/components/StockRadarDemo";

export const metadata: Metadata = {
  title: "رزق · تجربة رادار الأسهم",
  description: "صفحة تجريبية لجلب الأسهم النقية والمختلطة من Firestore وعرضها في جدول الرادار",
};

export default function RadarDemoPage() {
  return (
    <main>
      <StockRadarDemo />
    </main>
  );
}
