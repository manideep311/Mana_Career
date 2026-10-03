import Image from "next/image";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { PAGE_ART } from "@/lib/page-art";

/**
 * A weathered signpost in the fog fills the screen; one frosted card (like the
 * sign-in pages) carries the words, so they never sit on the busy picture.
 */
export default function NotFound() {
  const art = PAGE_ART.notFound;
  return (
    <main className="relative isolate flex min-h-screen items-end justify-center overflow-hidden bg-[#1c1730] px-5 py-8 sm:items-center lg:justify-end lg:px-20">
      <Image
        src={art.src}
        alt=""
        fill
        priority
        sizes="100vw"
        placeholder="blur"
        blurDataURL={art.blur}
        className="-z-10 object-cover object-[22%_50%] lg:object-center"
      />
      <div className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/90 px-7 py-9 shadow-[0_40px_90px_-30px_rgba(10,6,40,0.65)] backdrop-blur-xl sm:px-10">
        <p className="text-sm font-medium text-text-muted">Page not found</p>
        <h1 className="mt-2 font-display text-3xl text-text">This page isn&apos;t here</h1>
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          The link may be old, or the page may have moved. Your dashboard has everything
          you&apos;re working on.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/dashboard" className={buttonVariants()}>
            Go to your dashboard
          </Link>
          <Link href="/" className={buttonVariants({ variant: "ghost" })}>
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
