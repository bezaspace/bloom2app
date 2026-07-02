import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bloom2 — Practitioner",
  description: "Practitioner web app for Bloom2 wellness platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
