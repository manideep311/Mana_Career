import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mana Career",
  description: "Your career. Your next move. Smarter with AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
