import Image from "next/image";

import { cn } from "@/lib/cn";

export const HERO_ART_SRC = "/landing/hero-journey.webp";

// 24x14 WebP of the artwork, shown blurred until the real image arrives.
const BLUR =
  "data:image/webp;base64,UklGRqoAAABXRUJQVlA4IJ4AAACwBACdASoYAA4APtFUo0uoJKMhsAgBABoJbACdIHIxXb/4DxujC35CFoBTfOqQAP7HOMlA+YqHoU6WkYQty3GEvdVr0JqTAr1Vykii6yJPPwyF3K8tVTQi3239wjCgt/gBLsqohFtjsfCfQEuDdm3HVVLenqJcpiGw8/0YFXKCnI7MR651kiG0M7HvQ7NUyDuqdZfxkWVFp8nVcLwAAA==";

/**
 * The landing artwork: someone on a ridge at sunrise, a paper plane taking
 * off toward the city. Decorative (the headline carries the meaning), so the
 * alt text is empty. Served through next/image for right-sized, cached files.
 */
export function HeroArt({ className, sizes }: { className?: string; sizes: string }) {
  return (
    <Image
      src={HERO_ART_SRC}
      alt=""
      fill
      priority
      sizes={sizes}
      placeholder="blur"
      blurDataURL={BLUR}
      className={cn("object-cover", className)}
    />
  );
}
