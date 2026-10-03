import Image from "next/image";

import { PAGE_ART } from "@/lib/page-art";

const ART = PAGE_ART.auth;

/**
 * The account pages' backdrop: someone carving skills, opportunities, growth
 * and success into a cliff at sunrise. Decorative, so the alt text is empty.
 *
 * On wide screens the sharp picture is pinned so the carved stone ends right
 * at the card's left edge (the climber stays in full view), then it
 * fades out under the card; a soft, blurred copy fills the rest. The picture
 * is height-fitted, so the stone's right edge sits 306/1024 of the height
 * (29.9vh) in from the picture's right edge: the right offset is the layout's
 * gutter + card width (see `app/(auth)/layout.tsx`) minus that.
 */
export function AuthArt() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      <div className="absolute inset-0 hidden lg:block">
        <Image
          src={ART.src}
          alt=""
          fill
          sizes="25vw"
          className="scale-110 object-cover blur-2xl brightness-[0.55] saturate-[1.15]"
        />
        <div className="absolute inset-0 bg-[radial-gradient(70%_90%_at_100%_100%,rgba(90,74,227,0.45),rgba(90,74,227,0)_70%)]" />
      </div>

      <div className="absolute inset-0 lg:right-[calc(32rem-29.9vh)] lg:[mask-image:linear-gradient(90deg,#000_calc(100%-12rem),transparent)] xl:right-[calc(35rem-29.9vh)] 2xl:right-[calc(40rem-29.9vh)]">
        <Image
          src={ART.src}
          alt=""
          fill
          priority
          sizes="(min-width: 1024px) 75vw, 100vw"
          placeholder="blur"
          blurDataURL={ART.blur}
          className="object-cover object-[62%_50%] lg:object-right"
        />
      </div>

      {/* A lavender haze in the top corner keeps the wordmark readable. */}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(243,241,255,0.75)_0%,rgba(243,241,255,0.35)_14%,rgba(243,241,255,0)_28%)] lg:bg-[radial-gradient(40%_30%_at_0%_0%,rgba(243,241,255,0.75)_0%,rgba(243,241,255,0.35)_50%,rgba(243,241,255,0)_100%)]" />
    </div>
  );
}
