import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";

import { Toaster } from "@/components/ui/toaster";
import { AuthProvider } from "@/providers/AuthProvider";
import { QueryProvider } from "@/providers/QueryProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

// Display serif for headings only; body copy stays in Inter.
const newsreader = Newsreader({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display-serif",
});

export const metadata: Metadata = {
  title: "Mana Career",
  description:
    "A calm career companion: see where your experience can take you, what to work on next, and take the next step.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${newsreader.variable}`}>
        <QueryProvider>
          <AuthProvider>
            <Toaster>{children}</Toaster>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
