import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiDownload, apiErrorMessage, apiGet, triggerBrowserDownload } from "@/lib/api";
import type { ExportScopesResponse } from "@/lib/types";

// Export Project ZIP — real backend-generated archive (GET /api/export/source?scope=…).
// Honest states only: the success toast fires after the browser download actually starts.
export default function ExportZipDialog() {
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState("astraops");

  const scopesQ = useQuery({
    queryKey: ["export-scopes"],
    queryFn: () => apiGet<ExportScopesResponse>("/export/scopes"),
    enabled: open,
  });

  const exportMutation = useMutation({
    mutationFn: () => apiDownload(`/export/source?scope=${scope}`),
    onSuccess: (result) => {
      triggerBrowserDownload(result);
      toast.success(
        `Downloaded ${result.filename} (${Math.max(1, Math.round(result.blob.size / 1024))} KB) — see EXPORT_MANIFEST.json inside the archive`,
      );
    },
    onError: (error) => toast.error(apiErrorMessage(error)),
  });

  const scopes = scopesQ.data?.scopes ?? [];
  const active = scopes.find((s) => s.scope === scope);
  const policy = scopesQ.data?.policy;
  const pending = exportMutation.isPending;

  return (
    <>
      <Button size="sm" data-testid="export-zip-btn" onClick={() => setOpen(true)} disabled={pending}>
        <Download className="mr-1.5 h-3.5 w-3.5" />
        {pending ? "Exporting…" : "Export Project ZIP"}
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next: boolean) => {
          if (!pending) setOpen(next);
        }}
      >
        <DialogContent className="max-w-lg" data-testid="export-dialog">
          <DialogHeader>
            <DialogTitle>Export Project ZIP</DialogTitle>
            <DialogDescription>
              Generates a sanitized source archive server-side via{" "}
              <code className="font-mono text-xs">GET /api/export/source</code> and downloads it as a real ZIP.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="export-scope">Source scope</Label>
              <Select value={scope} onValueChange={setScope} disabled={pending}>
                <SelectTrigger data-testid="export-scope-select">
                  <SelectValue>
                    {(v: string) => scopes.find((s) => s.scope === v)?.label ?? "Select source"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {scopes.map((s) => (
                    <SelectItem key={s.scope} value={s.scope} disabled={!s.available}>
                      {s.label}
                      {s.available ? "" : " (unavailable in this deployment)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {active && (
                <p className="text-xs text-muted-foreground">
                  File: <span className="font-mono">{active.filename}</span>
                </p>
              )}
            </div>

            <div
              className="rounded-lg border border-[#1E2A44] bg-[#0A101E] p-3 text-xs text-muted-foreground"
              data-testid="export-policy-summary"
            >
              <p className="mb-1.5 flex items-center gap-1.5 font-medium text-[#7DD3FC]">
                <ShieldCheck className="h-3.5 w-3.5" /> Export policy (enforced server-side)
              </p>
              <ul className="list-disc space-y-1 pl-4">
                <li>
                  Excludes{" "}
                  {policy
                    ? `${policy.excluded_directories.slice(0, 6).join(", ")} and more`
                    : "node_modules, .git, venvs, caches, logs, archives"}
                </li>
                <li>Real .env files excluded; .env.example files pass a secret-redaction pass</li>
                <li>
                  Symlinks never followed; caps {(policy ? policy.max_file_bytes / 1024 / 1024 : 4).toFixed(0)} MB
                  per file, {(policy ? policy.max_total_bytes / 1024 / 1024 : 96).toFixed(0)} MB per archive
                </li>
                <li>Archive builds in a temp dir outside the project root, deleted after the download</li>
              </ul>
            </div>
          </div>

          <DialogFooter>
            <Button
              data-testid="export-confirm-btn"
              onClick={() => exportMutation.mutate()}
              disabled={pending || !active?.available}
            >
              {pending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating sanitized archive…
                </>
              ) : (
                <>
                  <Download className="mr-2 h-4 w-4" /> Download ZIP
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
