import { LiquidityDashboard } from "@/components/LiquidityDashboard";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function HomePage() {
  return (
    <main>
      <LiquidityDashboard />
    </main>
  );
}
