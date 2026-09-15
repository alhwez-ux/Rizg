import { CLIENT_BUILD } from "@/lib/auth/public-constants";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  return Response.json(
    { build: CLIENT_BUILD },
    {
      headers: {
        "Cache-Control": "private, no-store, no-cache, must-revalidate, max-age=0",
        "x-rizg-build": CLIENT_BUILD,
      },
    },
  );
}
