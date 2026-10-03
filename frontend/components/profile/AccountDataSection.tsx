"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { useRouter } from "next/navigation";

import { Download, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toaster";
import { ProblemError } from "@/lib/api/fetcher";
import { keepTabInside } from "@/lib/focus-trap";
import { useAuth } from "@/providers/AuthProvider";

const DELETED = [
  "Your profile, skills, experience, education and projects",
  "Every résumé you uploaded, the text read from it, and tailored versions",
  "Saved jobs, matches, roadmaps and applications with their letters and emails",
  "Your Mana AI conversations and activity",
];

// Long enough for any browser to start reading the file before it's released.
export const REVOKE_AFTER_MS = 60_000;

function filenameFrom(res: Response): string {
  const header = res.headers.get("content-disposition") ?? "";
  return /filename="([^"]+)"/.exec(header)?.[1] ?? "mana-career-export.zip";
}

/** Download a copy of everything as a ZIP (JSON + the uploaded PDFs). */
function DownloadData() {
  const { authedStream } = useAuth();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      const res = await authedStream("/api/v1/account/export");
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = filenameFrom(res);
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Revoking straight away can cancel the download in some browsers.
      setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
    } catch {
      toast({ title: "Couldn't prepare your download. Try again in a moment.", variant: "danger" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <h3 className="text-base font-semibold text-text">Your data</h3>
        <p>
          Download a copy of everything you&apos;ve added: a readable data file plus the
          résumé PDFs you uploaded.
        </p>
        <Button variant="outline" className="self-start" loading={busy} onClick={() => void download()}>
          <Download className="h-4 w-4" aria-hidden />
          Download your data
        </Button>
      </CardBody>
    </Card>
  );
}

/** The confirm step: password plus the typed word, then a one-way delete. */
function DeleteDialog({ onClose }: { onClose: () => void }) {
  const { api, logout } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const titleId = useId();
  const [password, setPassword] = useState("");
  const [word, setWord] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const ready = password.length > 0 && word === "DELETE";

  useEffect(() => {
    dialogRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
      else if (dialogRef.current) keepTabInside(e, dialogRef.current);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      await api.account.remove({ password, confirm: "DELETE" });
    } catch (err) {
      setBusy(false);
      setError(
        err instanceof ProblemError && err.code === "invalid_password"
          ? "That password isn't right."
          : "Something went wrong. Nothing was deleted; please try again.",
      );
      return;
    }
    await logout().catch(() => undefined);
    toast({ title: "Your account has been deleted." });
    router.push("/");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(21,19,31,0.45)] p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-[var(--shadow-2)] animate-rise"
      >
        <h2 id={titleId} className="font-display text-xl text-text">
          Delete your account?
        </h2>
        <p className="mt-2 text-sm text-text-muted">
          This can&apos;t be undone. Everything below is removed for good:
        </p>
        <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm text-text">
          {DELETED.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-text-muted">
          Want a copy first? Close this and use &ldquo;Download your data&rdquo;.
        </p>
        <form onSubmit={submit} className="mt-5 flex flex-col gap-4" noValidate>
          <Field id="delete-password" label="Your password" error={error ?? undefined}>
            <Input
              id="delete-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error ? true : undefined}
            />
          </Field>
          <Field id="delete-word" label="Type DELETE to confirm">
            <Input
              id="delete-word"
              autoComplete="off"
              value={word}
              onChange={(e) => setWord(e.target.value)}
            />
          </Field>
          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={busy} disabled={!ready}>
              Delete my account
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Profile page footer: take your data with you, or delete your account. */
export function AccountDataSection() {
  const [confirming, setConfirming] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function close() {
    setConfirming(false);
    triggerRef.current?.focus();
  }

  return (
    <section aria-labelledby="account-data-title" className="flex flex-col gap-4">
      <h2 id="account-data-title" className="text-lg font-semibold text-text">
        Your account
      </h2>
      <DownloadData />
      <Card className="border-danger/30">
        <CardBody className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-base font-semibold text-danger">
            <TriangleAlert className="h-4 w-4" aria-hidden />
            Danger zone
          </h3>
          <p>
            Permanently delete your account and everything in it. This can&apos;t be undone.
          </p>
          <Button
            ref={triggerRef}
            variant="danger"
            className="self-start"
            onClick={() => setConfirming(true)}
          >
            Delete account…
          </Button>
        </CardBody>
      </Card>
      {confirming ? <DeleteDialog onClose={close} /> : null}
    </section>
  );
}
