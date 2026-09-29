import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import config from "../../next.config";

describe("Next.js standalone output", () => {
  it("traces files relative to the frontend package", () => {
    expect(config.outputFileTracingRoot).toBe(resolve(process.cwd()));
  });
});
