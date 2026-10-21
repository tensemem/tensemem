export function jobStatusLabel(status: unknown): string {
  const raw = String(status ?? "");
  if (raw === "LEASED") return "In progress";
  if (raw === "QUEUED") return "Queued";
  if (raw === "DONE") return "Done";
  if (raw === "DEAD") return "Failed";
  return raw || "Unknown";
}

export function jobBadgeClass(status: unknown): string {
  const raw = String(status ?? "");
  if (raw === "DEAD") return "stop";
  if (raw === "DONE") return "act";
  if (raw === "LEASED") return "wait";
  return "wait";
}
