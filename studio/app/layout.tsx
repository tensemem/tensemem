import type { ReactNode } from "react";

import "./globals.css";
import { Nav } from "./nav";

export const metadata = {
  title: "TenseMem Studio",
  description: "Memory that knows its tenses",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main>{children}</main>
      </body>
    </html>
  );
}
