import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";

import { Toaster } from "@/components/ui/toaster";
import { AuthProvider } from "@/providers/AuthProvider";
import { QueryProvider } from "@/providers/QueryProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

// Bold display face for headings only; body copy stays in Inter.
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display-sans",
});

const DESCRIPTION =
  "A calm career companion: see where your experience can take you, what to work on next, and take the next step.";

// Link previews need absolute image URLs; the public address is set at build
// time (compose passes APP_BASE_URL). The images themselves are the
// `opengraph-image.jpg` / `twitter-image.jpg` files next to this layout.
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  title: "Mana Career",
  description: DESCRIPTION,
  openGraph: { type: "website", siteName: "Mana Career", title: "Mana Career", description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: "Mana Career", description: DESCRIPTION },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${jakarta.variable}`}>
        <QueryProvider>
          <AuthProvider>
            <Toaster>{children}</Toaster>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
