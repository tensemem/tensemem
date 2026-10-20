"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Board"],
  ["/memories", "Memories"],
  ["/playground", "Playground"],
  ["/lab", "Lab"],
  ["/map", "Map"],
  ["/echo", "Echo"],
  ["/ops", "Ops"],
] as const;

export function Nav() {
  const path = usePathname();
  return (
    <nav className="top">
      <strong>TenseMem Studio</strong>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} className={path === href ? "active" : ""}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
