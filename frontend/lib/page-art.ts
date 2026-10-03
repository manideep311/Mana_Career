/**
 * The illustrated scenes, one per page, all from the same world: a climber,
 * cliffs above a river city, sunrise. Files live in `public/art/` (1536x1024).
 *
 * `blur` is a 24x16 WebP shown blurred until the picture arrives. `focusY` is
 * the vertical object-position (%) that keeps the scene's subject in a wide
 * banner crop; banners are wider than the art, so only the vertical matters.
 */
export type PageArt = { src: string; blur: string; focusY: number };

const art = (name: string, blur: string, focusY = 50): PageArt => ({
  src: `/art/${name}.webp`,
  blur: `data:image/webp;base64,${blur}`,
  focusY,
});

export const PAGE_ART = {
  /** Sign in and the other account pages: carving the stone at sunrise. */
  auth: art(
    "carving-the-path",
    "UklGRrgAAABXRUJQVlA4IKwAAACQBACdASoYABAAPu1iqU2ppaQiMAgBMB2JbACdMoMYA0hhZ0tg3SBk75gU9gAA8ZjkwuaDb0bPNGpMuFICfH3r84ilAuwo5Try0l57r0F4UvCKdDO6P10YemRef+/aWvXcn46O003AfsKCJtHvcmagdGGR+aH6oW/1WTgs9umGQz4brq4nBWtoN2pwL1pjGtvewpJPyOZ+Yev884aA6sA20YFTluPYyc2AogAA",
  ),
  /** Dashboard: camp at dawn, a mug and a map (WelcomeBanner sets its own crop). */
  dashboard: art(
    "dawn-camp",
    "UklGRrYAAABXRUJQVlA4IKoAAADwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JagCdMoR3FfgWP+Bk7REPfjktl0V0wWAA/sJOwU5f8sK1JcFc1bK6WfT0fOJRPZ9o56jeg9zYMJlbDK9SLEnFjYX4NBQ5QgdZQB91IEVCY9WpF6OjJQ1JAyzeI4elkGCCp2/dVj9uPI30FwifIW1f3GfwHAJ67fjZ4aA4rfIAHS0lItmxEQkAznEgCIHFU7AAAA==",
  ),
  /** Résumé: a scroll unrolled on the rock, skills rising from it. */
  resume: art(
    "resume-scroll",
    "UklGRroAAABXRUJQVlA4IK4AAADwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoRwA8AVyo4SqrOh19AHWCuejcAA/tH0mVgaw2P2qinjJBFzAFI3uzQk3yy5o1bWHe19coMKVA80wHRHDjSGKoAUXTw9pD84ngqlBzA8uwuSxhWPjjUAy45oGSi8iNYZ/KP28I7i4lS6B1eZYsD0NDuuEWily6aoXn4VMEz/+q1YY/o4+wAA7nfLDfpPzvmSqAA=",
    50,
  ),
  /** Career paths: glowing trails branching toward different peaks. */
  careerPaths: art(
    "career-trails",
    "UklGRsoAAABXRUJQVlA4IL4AAADQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoR4PoArixuOQnlZ+ilApooQuAD6jOBLEOR2ktMlpkLiIl3WZdys43VqY+v/RoZpKBvY1dZHSb96O0ZuH2W37pLzSSqP9LOF2EImpENIJ0Rig69GnL3DS8CVM/wlEZqTrCyMG4o6f6+RtLNWalDYXoIfZAHnftAohBT+0y8UfpmnLX1h9mfz4I579ppmtqtJt9xqKPoF2uQzBvJsBY5oNAAA",
    29,
  ),
  /** One career path: a single trail of waymarkers up to the summit. */
  careerPath: art(
    "summit-trail",
    "UklGRtAAAABXRUJQVlA4IMQAAADQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoMYJn/Fr1t8h6IlA3KWfmgkgAD94pZl+Hseam8KMboxVA/cIoCKODn9QXG3k6D5ayjNuV94e/GA7RELWWEnTcjSbSOhp2B37GS73fZ1x9DlQt+VrL8xG1dpMycKy1pJ2Na0jeW8aEJboWir6aF69qsk37b3q/83C1697PE3jn2qjzxYpwLw7n5vYQ+EVB6Yx/+vAYdvspdeBxsasG6bpmM/zroUQAAA",
    15,
  ),
  /** Jobs: a telescope on the lookout, aimed at the city. */
  jobs: art(
    "city-lookout",
    "UklGRqoAAABXRUJQVlA4IJ4AAACwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JagCdMoR3CSAA5MMTHLWUnFMclDbAAP7AZ0VuEejj0hyebkcW/bE0dTU7n2zJTinrTKbPU91qqTmEq2vzrepJK0yOYi0YJ1xluymydfoEiQZYQ9Mc87sBegqMJZY+xbWf3iwbQKZy5lJ9Bcvi67+iss2CGMQo+wfkw2gNYyiMNYeUi3bAAA==",
    45,
  ),
  /** Applications: paper planes launched toward the city. */
  applications: art(
    "paper-planes",
    "UklGRrAAAABXRUJQVlA4IKQAAACQBACdASoYABAAPu1iqU2ppaQiMAgBMB2JagCdMoRwAkgBSszTPIB3IaAEGkYA/bxtAQTSeDf+6U9+sUScSAHUi2nmDavYI2HjSYEWix0ugiFHxG184/3SFJfTqjhr1N2qUo+mEcAjT06lYfYrN5hdpfLcXK7lcJGGmeDehbm+to/Ld3z0hO3r2q3eVEaEpTBNlUYcqy2i8m8hzKnGocS7jwAAAA==",
    46,
  ),
  /** Growth: higher up the cliff, looking back at the carved steps. */
  insights: art(
    "insights-ascent",
    "UklGRsAAAABXRUJQVlA4ILQAAAAwBQCdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoR4Lf/i2RXbMseZwlkQ/aNeWIyFyAD6D1eqQ3A0uRPT/WxP218W5NRqoQ1PjRh2KfSJZGs1N0PhNVo/uyuWRW97YYc7MOqajPK9RmHBNB39K5pYeCV96tCyg1tLe7OWzDfyLKef+qGiM5A4uGPrpGiYrJ9PjDPDLBqq5miGmAslk/0pH8b40G75BA2Wym5cEjKIItHYAAA=",
    24,
  ),
  /** Profile: the kit laid out on the rock, rope, compass, notebook, hammer. */
  profile: art(
    "profile-kit",
    "UklGRrYAAABXRUJQVlA4IKoAAADQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JaACdMoR4PoBXge9hDmMnT9K5u2RbIAD+v8XaWCuPA8ousgeOGW99eS9dykgbupZHWMoQ5mQUMYDtjtozgF6GY5kjBtpOyp1Ro3KwE3nLh7vk7ff76K99I5Fy5DyWHUXo2ERdtWN141R1YvtX3bl5SOvDcBal46nDchYq0UOGOykGyEghbeS0l2GU028ygPqAAA==",
    55,
  ),
  /** How it works, step 1: placing the scroll in the stone. */
  stepShare: art(
    "step-share",
    "UklGRroAAABXRUJQVlA4IK4AAACwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoGv/i2HWp6FPm0K6EQ4L154AP7M5qBFZC888+7jO6AW4JQPgNpwOiFMfkjaMVjm69lq5Wyu0h7btF+pHxva3Y9cCNlpcHS4Romzk9mbH0kQrhSbDZCT8HkhB65n7wx4m+CdhQHj4m4nGLvETWHrZ+CIHLDc1HNzA1mqfQnf9DIr6daFHgotJAt+AF7Fffc9tAA=",
  ),
  /** How it works, step 2: at the fork, trails to different peaks. */
  stepPaths: art(
    "step-paths",
    "UklGRsoAAABXRUJQVlA4IL4AAAAwBQCdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoRwAz/3zmcos1ui9mQxS0qom7x/gADLQgMot7AVWqnxT0odIn3OZLsW8i47nx238SCgxHGZ6WTcEPJwloIQB77ncLwO9Dr01GW0NyW8y1sENz5VxnDwCIdAlOMxVgdRKQCURygyl3wz46sboXrxH5/Zjzi29EFKsrJwbX76q075jd3G7tJj8uDthHksp7e4g6+WzmgW6T24dVDWxX7liiAA",
  ),
  /** How it works, step 3: carving the next steps. */
  stepPlan: art(
    "step-plan",
    "UklGRrwAAABXRUJQVlA4ILAAAADQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoMrin/Ab5iLa2PqQNjr/RsuAAD+7FPC6rQKC/x/1smIB8ZkyczIwB/9UD1M4UoqfYnWD/vMqWdBN6tl1dNgVkOeuDmkXxupXu/cP+xdXWIMH+uuLSbMR9z+mrH6HtHB7d1LV6KM/Qoii1YnawwitWugMi5r+wGB7kXcSb83sbFasn1yxTqy/uDr5VhQGTTjhEMoAA==",
  ),
  /** How it works, step 4: launching the paper plane. */
  stepApply: art(
    "step-apply",
    "UklGRrgAAABXRUJQVlA4IKwAAACwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoGvqgPkWHjCESCgZI9MrmAAAPRamV2/ZYzTwaxtCh0+zPIImA04jRHVa4PZRnGjSDd7OcUDe0Y1kRyOBBReIdPj2+LAJH2/n/1wc8XyzC6Of7qAQLBqbngdvDBPEWP0h/sWd07OLO8KA9duguv/rUP/TwCH8eR1B4SblIuoIzxjxINFndknIVl8YhwK44gA",
  ),
  /** Home page closing band: the violet flag on the summit. */
  ctaSummit: art(
    "cta-summit",
    "UklGRp4AAABXRUJQVlA4IJIAAABwBACdASoYABAAPu1iqk2ppaQiMAgBMB2JbACdMoR4GCFwygomh9KcACGOgADKoBrJi5QzgRROWGYMtJ+IbJb7RjGU4SJvGtg8ifHzhGQwQVlb9knhHT93zd1REJv3m1LWHw8TCdNXn6xreX2tXdTqbxYRQdab/K32Gutt9u+F6p+xCvScPRM0sxoUg4COJgAAAA==",
  ),
  /** No applications yet: a paper plane resting, ready to fly. */
  emptyApplications: art(
    "empty-applications",
    "UklGRq4AAABXRUJQVlA4IKIAAABwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoR3Ir+AZiPmIgGRIySkAADXNVXDchOv/GPOiB3l8cqWxBWVxOJ2YVrDeaY5pWEULVySU3eeeAfah95RbgbZUZZeP5oG8Z4X7IYaKxBVdO2YIJu7MkqLdtz63lM0W3Lk/jpE0Kp01PNYu7GcKzPe70jenoutrePh1g/Sx0kaouO9FDdEoAA=",
  ),
  /** No jobs match: a telescope aimed at drifting clouds. */
  emptyJobs: art(
    "empty-jobs",
    "UklGRq4AAABXRUJQVlA4IKIAAACQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoRwHu5t/8AwC/DJzTmUSgAA4YOmOoWfdNg+4fNq7K382NbXvis80OHHgNumRUvDS189cDjTvQWONgLFTprqBxlg1meVzEjPbEoXli/TwBRl4byMTXert3rylj7J7fUrl1DNQa0b026qraCjVImbz6XXlVfvpcSt2J2SGsQYi5jnJDG8AAA=",
  ),
  /** No paths yet: a lantern at the start of a misty trail. */
  emptyPaths: art(
    "empty-paths",
    "UklGRqwAAABXRUJQVlA4IKAAAABwBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoRwFf/gL4+I4tLZEXOgwAD+wAE48A/haHXWhmkbXPtTw/bMxxCvME3L8yXxzsuwIR5gO3X/Z1UEIY6kkz/3mJlYRLEpfRd/kHZhuwcCs5yinh1P1IzQZH+3EnlZ6YSndukzzdTZyBeZOg0P5/U0RAHP4QiBF6C1L/tkfDYeN4BegAAA",
  ),
  /** Not found: a weathered signpost in the fog. */
  notFound: art(
    "not-found",
    "UklGRqAAAABXRUJQVlA4IJQAAAAwBACdASoYABAAPu1iqU2ppaQiMAgBMB2JZgCsABVTUxPWfRiwSHSVAAAA9FMx9kjgQThNM4GH6hP4opxy2w+wiO85iDV0H+bwg67x3Vnt/WqnnfB9enq0Y61PtdwD4rNbfb+fO28bQHXBGEk3HINA/Yfe3wMvzQjTADBVkfSZGOQaPZh/+xh6fz6eCUdb+b3BsgAA",
  ),
  /** Something went wrong: a rockfall on the trail, a rope around it. */
  error: art(
    "error-rockfall",
    "UklGRrgAAABXRUJQVlA4IKwAAACQBACdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoRwFf/i2RSCI+XSkUhUvSAA/oN6Rtw71jaVlg/NYb6oUTTYgXbCWXoEzmbWpFBDi2SllKXbfWCHoW8ejY/blrBFLiYJRqw6+oG+2tSVID+cT2aXRzaJk08z6u5vIEeqy59y+a/prYfsKdip+pSs/Y0P1A9XtAO9RuWtzt3PFsg8R6kh2psu6YfFm1cFgAAA",
  ),
  /** An empty profile section: an open, empty backpack. */
  emptyProfile: art(
    "empty-profile",
    "UklGRrgAAABXRUJQVlA4IKwAAABQBQCdASoYABAAPu1iqU2ppaOiMAgBMB2JbACdMoR3Ff/qUFUBFCi3Y8eZ0kvsrGIbNCwA/n6Vt+uAJjTo1yqwvZB0l6J7LPj+EESQfxdfWv+2ac2tz8ZySIbjruWVGONTUYyOg0EaV0qWoR6bE7wgZvhlHEHo9U964Hx2rHAdvbMb3iiLQNntjGHbbDv98MO8Q3RhHdQbIO4pGgx5Dr24RK/Ac0nkcR/QAAAA",
  ),
} satisfies Record<string, PageArt>;
