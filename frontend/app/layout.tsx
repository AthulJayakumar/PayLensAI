/** Shared document shell and metadata for every PayLens route. */

import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "../components/AuthGate";

export const metadata: Metadata = {
  title: "PayLens — Payment Intelligence",
  description: "Deterministic payment analytics for merchant payment performance.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthGate>{children}</AuthGate></body>
    </html>
  );
}
