import Image from "next/image";

import { PAGE_ART } from "@/lib/page-art";

const ART = PAGE_ART.dashboard;

/**
 * The dashboard's greeting over a camp at dawn: someone with a mug and a map,
 * looking out at the city. The picture is decorative (empty alt).
 *
 * From `sm` up the words sit in the open sky to the right of the person, where
 * the sky runs from soft blue to peach and dark ink reads well on all of it;
 * on phones the banner is too short for that, so the words sit underneath.
 */
export function WelcomeBanner({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="relative overflow-hidden rounded-[24px] border border-border bg-surface shadow-[var(--shadow-2)]">
      <div className="relative h-40 sm:h-auto sm:aspect-[5/2]">
        <Image
          src={ART.src}
          alt=""
          fill
          priority
          sizes="(min-width: 768px) 768px, 100vw"
          placeholder="blur"
          blurDataURL={ART.blur}
          className="object-cover object-[40%_30%] sm:object-[50%_8%]"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 hidden bg-[radial-gradient(70%_85%_at_80%_0%,rgba(243,241,255,0.78)_0%,rgba(243,241,255,0.5)_45%,rgba(243,241,255,0)_75%)] sm:block"
        />
      </div>
      <div className="flex flex-col gap-1 px-5 py-4 sm:absolute sm:right-0 sm:top-0 sm:w-[54%] sm:px-7 sm:py-6">
        <h1 className="font-display text-2xl text-text sm:text-3xl">{title}</h1>
        <p className="text-sm text-text-muted sm:text-text/80">{subtitle}</p>
      </div>
    </header>
  );
}
