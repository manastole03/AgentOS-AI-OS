"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { Textarea } from "@healthos/ui/textarea";
import { Bot, Send, ShieldCheck, UserRound } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { PageHeading } from "@/components/portal/page-heading";

interface AIRun {
  id: string;
  status: string;
  selected_team?: string;
  response?: string;
}
interface Message {
  role: "user" | "assistant";
  content: string;
}

export function AIAssistant() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const prompt = String(form.get("prompt") || "").trim();
    if (!prompt) return;
    setMessages((items) => [...items, { role: "user", content: prompt }]);
    setBusy(true);
    setError(null);
    event.currentTarget.reset();
    try {
      const run = await authenticatedFetch<AIRun>("/ai/v1/runs", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          execution_mode: "sync",
          memory_mode: "read",
        }),
      });
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: run.response || "The agent completed without a response.",
        },
      ]);
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "AI assistant unavailable",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="HealthOS intelligence"
        title="AI Assistant"
        description="Coordinate clinical, insurance, administrative, and document intelligence agents with authorized context."
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        <Card className="min-h-[600px]">
          <CardContent className="flex min-h-[600px] flex-col p-0">
            <div className="flex-1 space-y-5 p-5 md:p-7">
              {messages.length ? (
                messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
                  >
                    {message.role === "assistant" ? (
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-950 text-emerald-400">
                        <Bot className="size-5" />
                      </span>
                    ) : null}
                    <div
                      className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                    >
                      {message.content}
                    </div>
                    {message.role === "user" ? (
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                        <UserRound className="size-5" />
                      </span>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="grid h-96 place-items-center text-center">
                  <div>
                    <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-950 text-emerald-400">
                      <Bot className="size-7" />
                    </span>
                    <h2 className="mt-4 font-semibold">
                      How can the agent teams help?
                    </h2>
                    <p className="mt-2 max-w-md text-sm text-muted-foreground">
                      Ask for evidence synthesis, documentation support,
                      insurance navigation, or document analysis.
                    </p>
                  </div>
                </div>
              )}
              {busy ? (
                <p className="text-sm text-muted-foreground">
                  Agent teams are working…
                </p>
              ) : null}
              {error ? <p className="text-sm text-red-600">{error}</p> : null}
            </div>
            <form onSubmit={submit} className="border-t p-4">
              <Textarea
                name="prompt"
                required
                placeholder="Ask HealthOS…"
                className="min-h-24"
              />
              <div className="mt-3 flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Do not include data you are not authorized to access.
                </p>
                <Button disabled={busy}>
                  Send <Send className="ml-2 size-4" />
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="size-5 text-primary" />
              Safety controls
            </CardTitle>
            <CardDescription>
              Human oversight remains mandatory.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-muted-foreground">
            <p>• No autonomous diagnosis or treatment decisions.</p>
            <p>• No final insurance coverage determinations.</p>
            <p>• Tenant-scoped retrieval and audit logging.</p>
            <p>• Evidence citations and uncertainty disclosure.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
