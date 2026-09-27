import net from "node:net";
import { env as runtimeEnv } from "node:process";
import tls from "node:tls";

import { NextResponse } from "next/server";

import { RECOVERY_EMAIL, isRecoveryEmail, randomCode } from "@/lib/auth";
import { ensureGate, saveResetCode } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

type Delivery = "email" | "telegram" | "failed";

function runtimeValue(name: string): string {
  const source = runtimeEnv as unknown as Record<string, string | undefined>;
  return String(source[name] ?? "").trim();
}

function mailEnv() {
  return {
    sender: runtimeValue("SENDER_EMAIL"),
    password: runtimeValue("SENDER_PASSWORD"),
    host: runtimeValue("SMTP_SERVER") || "smtp.gmail.com",
    port: Number(runtimeValue("SMTP_PORT") || "587"),
    token: runtimeValue("TELEGRAM_BOT_TOKEN"),
    chatId: runtimeValue("TELEGRAM_CHAT_ID"),
  };
}

function smtpCommand(socket: net.Socket, command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const onData = (chunk: Buffer) => {
      chunks.push(chunk);
      const text = Buffer.concat(chunks).toString("utf8");
      if (/^\d{3} /m.test(text)) {
        socket.off("data", onData);
        resolve(text);
      }
    };
    socket.on("data", onData);
    socket.once("error", reject);
    if (command) socket.write(`${command}\r\n`);
  });
}

async function sendEmail(code: string): Promise<boolean> {
  const { sender: user, password: pass, host, port } = mailEnv();
  if (!user || !pass || !Number.isFinite(port)) return false;
  const subject = `=?UTF-8?B?${Buffer.from("رمز استعادة رزق").toString("base64")}?=`;
  const message = [
    `From: ${user}`,
    `To: ${RECOVERY_EMAIL}`,
    `Subject: ${subject}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "",
    `رمز استعادة الرقم السري لرادار رزق: ${code}`,
    "صالح لمدة 15 دقيقة. إذا لم تطلب هذا الرمز فتجاهل الرسالة.",
  ].join("\r\n");
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const finish = (ok: boolean) => {
      socket.end();
      resolve(ok);
    };
    socket.setTimeout(12_000, () => finish(false));
    socket.once("error", () => finish(false));
    void (async () => {
      try {
        await smtpCommand(socket, "");
        const greeting = await smtpCommand(socket, "EHLO rizg.vercel.app");
        if (!greeting.includes("STARTTLS")) return finish(false);
        await smtpCommand(socket, "STARTTLS");
        const secure = tls.connect({ socket, servername: host });
        await new Promise<void>((done, reject) => {
          secure.once("secureConnect", () => done());
          secure.once("error", reject);
        });
        const talk = (command: string) => smtpCommand(secure, command);
        await talk("EHLO rizg.vercel.app");
        const auth = await talk("AUTH LOGIN");
        if (!auth.startsWith("334")) return finish(false);
        await talk(Buffer.from(user).toString("base64"));
        const logged = await talk(Buffer.from(pass).toString("base64"));
        if (!logged.startsWith("235")) return finish(false);
        await talk(`MAIL FROM:<${user}>`);
        await talk(`RCPT TO:<${RECOVERY_EMAIL}>`);
        await talk("DATA");
        const sent = await talk(`${message}\r\n.`);
        await talk("QUIT");
        finish(sent.startsWith("250"));
      } catch {
        finish(false);
      }
    })();
  });
}

async function sendTelegram(code: string): Promise<{ ok: boolean; reason: string }> {
  const { token, chatId } = mailEnv();
  if (!token || !chatId) return { ok: false, reason: "missing" };
  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(8000),
      body: JSON.stringify({
        chat_id: chatId,
        text: `رمز استعادة الرقم السري لرادار رزق: ${code}\nصالح لمدة 15 دقيقة. إذا لم تطلب هذا الرمز فتجاهله.`,
      }),
    });
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; description?: string } | null;
    if (response.ok && payload?.ok === true) return { ok: true, reason: "sent" };
    const description = String(payload?.description || "denied").slice(0, 80);
    return { ok: false, reason: description.includes(token) ? "denied" : description };
  } catch {
    return { ok: false, reason: "error" };
  }
}

async function deliverRecoveryCode(code: string): Promise<{ delivery: Delivery; reason: string }> {
  if (await sendEmail(code)) return { delivery: "email", reason: "sent" };
  const telegram = await sendTelegram(code);
  if (telegram.ok) return { delivery: "telegram", reason: "sent" };
  return { delivery: "failed", reason: telegram.reason };
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { email?: unknown } | null;
  const email = String(body?.email ?? "");
  if (!isRecoveryEmail(email)) {
    return NextResponse.json({ message: "unknown_email" }, { status: 422 });
  }
  const gate = await ensureGate();
  if (!gate) {
    return NextResponse.json({ message: "not_configured" }, { status: 409 });
  }
  const code = randomCode(6);
  await saveResetCode(code);
  if (process.env.NODE_ENV !== "production") {
    console.info(`[rizg-auth] recovery code for ${RECOVERY_EMAIL}: ${code}`);
  }
  const result = await deliverRecoveryCode(code);
  return NextResponse.json({
    ok: true,
    delivered: result.delivery !== "failed",
    delivery: result.delivery,
    reason: result.delivery === "failed" ? result.reason : "",
    recoveryEmail: RECOVERY_EMAIL,
  });
}
