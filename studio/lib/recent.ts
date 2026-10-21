const PREFIX = "tensemem_recent_";

export function recentList(kind: string): string[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(PREFIX + kind) ?? "[]");
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is string => typeof item === "string" && item.trim() !== "");
  } catch {
    return [];
  }
}

export function rememberRecent(kind: string, value: string): void {
  const text = value.trim();
  if (!text) {
    return;
  }
  const next = [text, ...recentList(kind).filter((item) => item !== text)].slice(0, 12);
  try {
    localStorage.setItem(PREFIX + kind, JSON.stringify(next));
  } catch {
    // Suggestions are optional.
  }
}

export function matchesRecent(kind: string, typed: string): string[] {
  const query = typed.trim().toLowerCase();
  const all = recentList(kind);
  if (!query) {
    return all.slice(0, 6);
  }
  return all.filter((item) => item.toLowerCase().includes(query)).slice(0, 6);
}
