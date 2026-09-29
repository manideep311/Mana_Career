import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

const STEPS = [
  {
    title: "Share your résumé",
    body: "We read it and map your experience and skills. You check what we found before anything uses it.",
  },
  {
    title: "See where it can take you",
    body: "The paths your experience points to, why each one fits, and what's missing, in plain words.",
  },
  {
    title: "Get a practical plan",
    body: "The few skills worth building next, each with a project to prove it, laid out over the next 30 to 90 days.",
  },
  {
    title: "Take the next step",
    body: "Tailor your résumé to a role and prepare an application. Nothing is sent without your approval.",
  },
];

const PRINCIPLES = [
  {
    title: "Grounded in your real experience",
    body: "Suggestions point back to your own words. We never invent achievements, metrics, skills or titles, and we tell you when there isn't enough to go on.",
  },
  {
    title: "Honest about the gap",
    body: "A path is a close fit, a reachable stretch or a significant pivot, with the reasons shown. No made-up odds.",
  },
  {
    title: "You stay in control",
    body: "You decide which direction to pursue, and every application waits for your approval before it goes anywhere.",
  },
];

/** A quiet line from where you are to where you want to be. Decorative. */
function JourneyLine() {
  const stops = ["Where you are", "Next 30 days", "60 to 90 days", "Where you want to be"];
  return (
    <figure aria-hidden="true" className="relative mx-auto w-full max-w-xs">
      <svg viewBox="0 0 240 300" className="h-auto w-full text-accent">
        <path
          d="M40 270 C 40 200, 200 210, 190 150 S 60 90, 80 30"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray="4 6"
          strokeLinecap="round"
        />
        {[
          [40, 270],
          [142, 198],
          [124, 90],
          [80, 30],
        ].map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={i === 3 ? 7 : 5}
            fill={i === 3 ? "currentColor" : "var(--surface)"}
            stroke="currentColor"
            strokeWidth="1.5"
          />
        ))}
      </svg>
      <ol className="absolute inset-0 text-xs text-text-muted">
        <li className="absolute left-[22%] top-[87%]">{stops[0]}</li>
        <li className="absolute left-[62%] top-[68%]">{stops[1]}</li>
        <li className="absolute right-[54%] top-[27%] text-right">{stops[2]}</li>
        <li className="absolute left-[38%] top-[6%] font-medium text-text">{stops[3]}</li>
      </ol>
    </figure>
  );
}

export default function Page() {
  return (
    <div className="min-h-screen bg-bg">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <span className="font-display text-xl text-text">Mana Career</span>
        <Link href="/login" className="text-sm font-medium text-text-muted hover:text-text">
          Sign in
        </Link>
      </header>

      <main>
        <section className="mx-auto grid max-w-5xl items-center gap-12 px-6 pb-20 pt-10 md:grid-cols-[1.4fr_1fr] md:pt-16">
          <div className="flex flex-col gap-6">
            <h1 className="font-display text-5xl leading-[1.05] text-text md:text-6xl">
              Build the career you actually want
            </h1>
            <p className="max-w-xl text-lg leading-relaxed text-text-muted">
              Mana Career reads your experience, shows the paths it points to and what
              stands in the way, then turns that into a plan you can start this week.
              You decide every step.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <Link href="/register" className={buttonVariants({ size: "lg" })}>
                Build my career path
              </Link>
              <a href="#how-it-works" className={buttonVariants({ variant: "ghost", size: "lg" })}>
                Explore how it works
              </a>
            </div>
          </div>
          <JourneyLine />
        </section>

        <section
          id="how-it-works"
          aria-labelledby="how-title"
          className="scroll-mt-8 border-y border-border bg-surface"
        >
          <div className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-20">
            <div className="flex max-w-2xl flex-col gap-3">
              <h2 id="how-title" className="font-display text-3xl text-text">
                From &ldquo;I&apos;m not sure&rdquo; to &ldquo;I know what to do next&rdquo;
              </h2>
              <p className="text-base text-text-muted">
                Four steps, at your pace. Each one builds on what you already have.
              </p>
            </div>
            <ol className="grid gap-8 md:grid-cols-4">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex flex-col gap-2">
                  <span className="font-display text-2xl text-accent">{i + 1}</span>
                  <h3 className="text-base font-semibold text-text">{step.title}</h3>
                  <p className="text-sm leading-relaxed text-text-muted">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-labelledby="principles-title" className="mx-auto max-w-5xl px-6 py-20">
          <h2 id="principles-title" className="font-display text-3xl text-text">
            What you can count on
          </h2>
          <ul className="mt-8 grid gap-8 md:grid-cols-3">
            {PRINCIPLES.map((p) => (
              <li key={p.title} className="flex flex-col gap-2 border-t border-border pt-4">
                <h3 className="text-base font-semibold text-text">{p.title}</h3>
                <p className="text-sm leading-relaxed text-text-muted">{p.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mx-auto flex max-w-5xl flex-col items-start gap-5 px-6 pb-24">
          <p className="font-display text-3xl text-text">Start with what you already have.</p>
          <Link href="/register" className={buttonVariants({ size: "lg" })}>
            Start my career journey
          </Link>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-6 text-sm text-text-muted">
          <span className="font-display text-base text-text">Mana Career</span>
          <nav aria-label="Account" className="flex gap-5">
            <Link href="/login" className="hover:text-text">
              Sign in
            </Link>
            <Link href="/register" className="hover:text-text">
              Create an account
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
