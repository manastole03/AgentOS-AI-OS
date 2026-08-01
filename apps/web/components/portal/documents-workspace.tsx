"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { DocumentAsset } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { Input } from "@healthos/ui/input";
import { Label } from "@healthos/ui/label";
import {
  Download,
  FileSearch,
  FileText,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { authenticatedFetch, getCookie } from "@/lib/auth";
import { env } from "@/lib/env";
import { PageHeading } from "@/components/portal/page-heading";

export function DocumentsWorkspace() {
  const [items, setItems] = useState<DocumentAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    async () =>
      setItems(
        await authenticatedFetch<DocumentAsset[]>("/api/v1/portal/documents"),
      ),
    [],
  );
  useEffect(() => {
    void load().catch((value: unknown) =>
      setError(
        value instanceof Error ? value.message : "Unable to load documents",
      ),
    );
  }, [load]);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = new FormData(event.currentTarget);
      await authenticatedFetch("/api/v1/portal/documents", {
        method: "POST",
        body,
      });
      event.currentTarget.reset();
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  async function download(item: DocumentAsset) {
    const headers = new Headers();
    const csrf = getCookie("healthos_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
    const response = await fetch(
      `${env.NEXT_PUBLIC_API_URL}/api/v1/portal/documents/${item.id}/content`,
      { credentials: "include", headers },
    );
    if (!response.ok) throw new Error("Download failed");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = item.filename;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHeading
        eyebrow="Document intelligence"
        title="Secure documents"
        description="Upload healthcare and insurance files, extract searchable text with OCR, and retain a controlled source of truth."
      />
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Upload document</CardTitle>
          <CardDescription>
            PDF, image, text, and structured healthcare files up to 10 MB.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={upload}
            className="grid gap-4 sm:grid-cols-[1fr_220px_auto] sm:items-end"
          >
            <div className="space-y-2">
              <Label htmlFor="file">Document</Label>
              <Input id="file" name="file" type="file" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <select
                id="category"
                name="category"
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              >
                <option>general</option>
                <option>clinical</option>
                <option>insurance</option>
                <option>billing</option>
                <option>identity</option>
              </select>
            </div>
            <Button disabled={busy}>
              <UploadCloud className="mr-2 size-4" />
              {busy ? "Processing…" : "Upload & OCR"}
            </Button>
          </form>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex gap-4 p-5">
              <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                <FileText />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="truncate font-medium">{item.filename}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {(item.byte_size / 1024).toFixed(1)} KB ·{" "}
                      {new Date(item.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge variant="secondary" className="capitalize">
                    {item.status}
                  </Badge>
                </div>
                {item.ocr_text ? (
                  <div className="mt-4 rounded-lg bg-muted/50 p-3">
                    <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <FileSearch className="size-3" />
                      OCR preview
                    </p>
                    <p className="line-clamp-3 text-xs leading-relaxed">
                      {item.ocr_text}
                    </p>
                  </div>
                ) : null}
                <div className="mt-4 flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void download(item)}
                  >
                    <Download className="mr-2 size-4" />
                    Download
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={async () => {
                      if (!window.confirm("Permanently delete this document?"))
                        return;
                      await authenticatedFetch(
                        `/api/v1/portal/documents/${item.id}`,
                        { method: "DELETE" },
                      );
                      await load();
                    }}
                  >
                    <Trash2 className="size-4" />
                    <span className="sr-only">Delete</span>
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {!items.length ? (
          <div className="col-span-full rounded-xl border border-dashed p-14 text-center text-sm text-muted-foreground">
            No documents uploaded yet.
          </div>
        ) : null}
      </div>
    </>
  );
}
