import Image from "next/image";
import Link from "next/link";
import { Dancing_Script } from "next/font/google";

import {
  ArrowRight,
  BarChart3,
  Briefcase,
  Compass,
  FileText,
  GraduationCap,
  Lightbulb,
  Repeat,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { HeroArt } from "@/components/landing/HeroArt";
import { HowItWorksPlayer } from "@/components/landing/HowItWorksPlayer";
import { StatsStrip } from "@/components/landing/StatsStrip";
import { PAGE_ART } from "@/lib/page-art";

// One script face, used sparingly: the accent word in the headline.
const script = Dancing_Script({ subsets: ["latin"], display: "swap", variable: "--font-hand-script" });

const NAV = [
  { href: "#features", label: "Features" },
  { href: "#career-paths", label: "Career Paths" },
  { href: "#how-it-works", label: "How it Works" },
];

const FEATURES: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: UserRound,
    title: "Understand yourself",
    body: "See the skills your résumé actually shows, and the ones that are only listed without proof.",
  },
  {
    icon: Compass,
    title: "Explore career paths",
    body: "Role families your experience points to, with why each fits, what you have and what's missing.",
  },
  {
    icon: BarChart3,
    title: "Build skills",
    body: "The few skills worth building next, each with a small project to prove it and a resource to learn from.",
  },
  {
    icon: Lightbulb,
    title: "Get guidance",
    body: "Up to three next steps, most useful first, always tied to your own data. No generic advice.",
  },
  {
    icon: FileText,
    title: "Strengthen your résumé",
    body: "Each issue as a problem, why it matters and a suggestion, quoting your own lines. Nothing invented.",
  },
  {
    icon: Briefcase,
    title: "Find opportunities",
    body: "Roles that fit, explained in words, and applications that wait for your approval before anything is sent.",
  },
];

const PATHS = [
  "Backend Engineer",
  "Frontend Engineer",
  "Full-Stack Engineer",
  "Data Analyst",
  "Data Scientist",
  "Data Engineer",
  "Machine Learning Engineer",
  "MLOps Engineer",
  "Platform Engineer",
  "Research Scientist",
  "Engineering Manager",
];

const STEPS = [
  {
    art: PAGE_ART.stepShare,
    title: "Share your résumé",
    body: "We read it and map your experience and skills. You check what we found before anything uses it.",
  },
  {
    art: PAGE_ART.stepPaths,
    title: "See where it can take you",
    body: "The paths your experience points to, why each one fits, and what's missing, in plain words.",
  },
  {
    art: PAGE_ART.stepPlan,
    title: "Get a practical plan",
    body: "The few skills worth building next, each with a project to prove it, laid out over the next 30 to 90 days.",
  },
  {
    art: PAGE_ART.stepApply,
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

function LogoMark({ id }: { id: string }) {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5a4ae3" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <path
        d="M4 7 L4 24 L16 16 L28 24 L28 7 L16 15 Z"
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Wordmark({ id }: { id: string }) {
  return (
    <Link href="/" aria-label="Mana Career home" className="flex items-center gap-2">
      <LogoMark id={id} />
      <span className="font-display text-xl text-text">ManaCareer</span>
    </Link>
  );
}

// No display utility here: each use sets its own (the header hides it on phones).
const primaryCta =
  "items-center justify-center gap-2 rounded-xl bg-accent font-semibold text-accent-fg shadow-[0_10px_24px_rgba(90,74,227,0.32)] transition hover:brightness-110";

export default function Page() {
  return (
    <div className={`${script.variable} min-h-screen bg-surface`}>
      {/* ------------------------------------------------------------ hero */}
      <section className="relative overflow-hidden xl:min-h-[880px]">
        <header className="relative z-20 mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-5">
          <Wordmark id="logo-head" />
          <nav aria-label="Sections" className="hidden items-center gap-9 text-[15px] text-text lg:flex">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="hover:text-accent">
                {n.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="inline-flex h-11 items-center rounded-xl border border-border bg-white/85 px-5 text-[15px] font-medium text-text backdrop-blur hover:bg-white"
            >
              Sign in
            </Link>
            <Link href="/register" className={`${primaryCta} hidden h-11 px-5 text-[15px] sm:inline-flex`}>
              Get Started
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </header>

        <div className="mx-auto max-w-7xl px-6 pb-16 pt-8 md:pt-14">
          <div className="relative z-10 flex max-w-[40rem] flex-col gap-7 xl:max-w-[42rem]">
            <p className="self-start rounded-full border border-border bg-white/90 px-3.5 py-2 text-[12.5px] font-medium text-text shadow-[var(--shadow-1)] sm:px-4 sm:text-sm">
              Your Career. <span className="text-accent">More Clarity.</span> More Possibilities.
            </p>
            <h1 className="font-display text-[3.1rem] font-extrabold leading-[1.02] tracking-[-0.035em] text-text sm:text-6xl md:text-7xl">
              Build the career <br className="hidden sm:inline" />
              you{" "}
              {/* Script accent: padded so the gradient covers the swashes, and
                  normal tracking so the letters still join. */}
              <span className="inline-block bg-gradient-to-r from-accent to-accent-2 bg-clip-text px-[0.04em] pb-[0.1em] font-hand text-[1.16em] font-bold leading-[0.9] tracking-normal text-transparent">
                actually
              </span>{" "}
              want<span className="-ml-[0.05em]">.</span>
            </h1>
            <p className="max-w-xl text-lg leading-relaxed text-text-muted md:text-xl">
              Understand your strengths, explore real career paths, improve your résumé, and get
              clear next steps, all in one place.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <Link href="/register" className={`${primaryCta} inline-flex h-14 px-8 text-lg`}>
                Start My Career Journey
                <ArrowRight className="h-5 w-5" aria-hidden />
              </Link>
              <HowItWorksPlayer />
            </div>
          </div>

          {/* One image for every width: a card under the text below xl, a
              faded side panel behind the hero from xl up. */}
          <div className="relative mt-10 aspect-video overflow-hidden rounded-2xl shadow-[var(--shadow-2)] xl:absolute xl:inset-y-0 xl:left-[30%] xl:right-0 xl:mt-0 xl:aspect-auto xl:rounded-none xl:shadow-none xl:[mask-image:linear-gradient(to_right,transparent,black_28%)]">
            <HeroArt
              sizes="(min-width: 1280px) 70vw, (min-width: 768px) 90vw, 100vw"
              className="object-[70%_50%] xl:object-[78%_50%]"
            />
            <div className="absolute bottom-8 right-8 hidden xl:flex items-center gap-3 text-sm font-medium text-white [text-shadow:0_1px_6px_rgba(20,16,40,0.6)]">
              <span className="flex -space-x-2" aria-hidden>
                {[GraduationCap, Briefcase, Repeat].map((Icon, i) => (
                  <span
                    key={i}
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-white/20 ring-2 ring-white/70 backdrop-blur"
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                ))}
              </span>
              <span className="max-w-[15rem] leading-snug">
                Built for students, professionals and career changers.
              </span>
            </div>
          </div>

          <div className="relative z-10 mt-12 md:mt-20">
            <StatsStrip />
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- features */}
      <section id="features" aria-labelledby="features-title" className="scroll-mt-4 bg-bg">
        <div className="mx-auto flex max-w-7xl flex-col gap-12 px-6 py-24">
          <div className="flex max-w-2xl flex-col gap-3">
            <h2 id="features-title" className="font-display text-4xl text-text">
              Everything you need for the next step
            </h2>
            <p className="text-lg text-text-muted">
              One place that connects your résumé, the paths it points to, and a plan you can
              actually follow.
            </p>
          </div>
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <li
                key={title}
                className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-6 shadow-[var(--shadow-1)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-2)]"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <h3 className="text-lg font-semibold text-text">{title}</h3>
                <p className="text-sm leading-relaxed text-text-muted">{body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---------------------------------------------------- career paths */}
      <section id="career-paths" aria-labelledby="paths-title" className="scroll-mt-4">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-6 py-24 lg:grid-cols-2">
          <div className="flex flex-col gap-4">
            <h2 id="paths-title" className="font-display text-4xl text-text">
              Career paths, explained
            </h2>
            <p className="text-lg leading-relaxed text-text-muted">
              We group real job postings into role families and compare them with your
              experience. Each path shows why it fits, what you already have, what&apos;s
              missing, and how big a move it is.
            </p>
            <ul className="flex flex-wrap gap-2 text-sm">
              <li className="rounded-full bg-positive-soft px-3 py-1 font-medium text-positive">Close fit</li>
              <li className="rounded-full bg-accent-soft px-3 py-1 font-medium text-accent">Reachable stretch</li>
              <li className="rounded-full bg-surface-sunk px-3 py-1 font-medium text-text-muted">
                Significant pivot
              </li>
            </ul>
          </div>
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium text-text-muted">Paths we map include</p>
            <ul className="flex flex-wrap gap-2.5">
              {PATHS.map((p) => (
                <li
                  key={p}
                  className="rounded-full border border-border bg-surface px-4 py-2 text-sm font-medium text-text shadow-[var(--shadow-1)]"
                >
                  {p}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------- how it works */}
      <section id="how-it-works" aria-labelledby="how-title" className="scroll-mt-4 bg-bg">
        <div className="mx-auto flex max-w-7xl flex-col gap-12 px-6 py-24">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="flex max-w-2xl flex-col gap-3">
              <h2 id="how-title" className="font-display text-4xl text-text">
                From &ldquo;I&apos;m not sure&rdquo; to &ldquo;I know what to do next&rdquo;
              </h2>
              <p className="text-lg text-text-muted">
                Four steps, at your pace. Each one builds on what you already have.
              </p>
            </div>
            <HowItWorksPlayer />
          </div>
          <ol className="grid gap-8 md:grid-cols-4">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex flex-col gap-3">
                <div className="relative mb-2 aspect-[3/2] overflow-hidden rounded-2xl shadow-[var(--shadow-2)]">
                  <Image
                    src={step.art.src}
                    alt=""
                    fill
                    sizes="(min-width: 768px) 25vw, 100vw"
                    placeholder="blur"
                    blurDataURL={step.art.blur}
                    className="object-cover"
                  />
                  <span className="absolute left-3 top-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent text-base font-bold text-accent-fg shadow-[0_6px_16px_rgba(30,20,90,0.45)] ring-2 ring-white/80">
                    {i + 1}
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-text">{step.title}</h3>
                <p className="text-sm leading-relaxed text-text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ------------------------------------------------------ principles */}
      <section aria-labelledby="principles-title" className="mx-auto max-w-7xl px-6 py-24">
        <h2 id="principles-title" className="font-display text-4xl text-text">
          What you can count on
        </h2>
        <ul className="mt-10 grid gap-10 md:grid-cols-3">
          {PRINCIPLES.map((p) => (
            <li key={p.title} className="flex flex-col gap-2 border-t-2 border-accent/30 pt-5">
              <h3 className="text-lg font-semibold text-text">{p.title}</h3>
              <p className="text-sm leading-relaxed text-text-muted">{p.body}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* ------------------------------------------------------------- CTA */}
      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="relative isolate flex overflow-hidden rounded-3xl bg-[#2a1f63] px-8 py-14 text-accent-fg md:min-h-[24rem] md:items-center md:px-14">
          <Image
            src={PAGE_ART.ctaSummit.src}
            alt=""
            fill
            sizes="(min-width: 1280px) 1232px, 100vw"
            placeholder="blur"
            blurDataURL={PAGE_ART.ctaSummit.blur}
            className="-z-10 object-cover object-[20%_62%]"
          />
          {/* A deep violet veil where the words sit, so white text reads on the bright sky. */}
          <div
            aria-hidden="true"
            className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgba(32,22,90,0.55),rgba(32,22,90,0.8))] md:bg-[linear-gradient(90deg,rgba(32,22,90,0)_15%,rgba(32,22,90,0.55)_45%,rgba(32,22,90,0.85)_100%)]"
          />
          <div className="flex flex-col items-start gap-6 md:ml-auto md:max-w-md">
            <div className="flex flex-col gap-2">
              <p className="font-display text-3xl md:text-4xl">Start with what you already have.</p>
              <p className="text-base text-white/90">Upload your résumé and see your first next step.</p>
            </div>
            <Link
              href="/register"
              className="inline-flex h-14 items-center gap-2 rounded-xl bg-white px-8 text-lg font-semibold text-accent shadow-[var(--shadow-2)] transition hover:bg-white/90"
            >
              Build my career path
              <ArrowRight className="h-5 w-5" aria-hidden />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-text-muted">
          <Wordmark id="logo-foot" />
          <nav aria-label="Account" className="flex gap-6">
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
