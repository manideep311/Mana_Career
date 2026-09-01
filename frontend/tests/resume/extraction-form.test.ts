import { describe, expect, it } from "vitest";

import { toExtraction, toFormValues } from "@/lib/resume/extraction-form";

describe("extraction-form converters", () => {
  it("round-trips scalars and csv arrays", () => {
    const e = {
      full_name: "Jane Doe",
      skills: ["Python", "PyTorch"],
      experiences: [{ company: "Acme", title: "ML Eng", highlights: ["shipped x"], tech: ["py"] }],
    };
    const v = toFormValues(e);
    expect(v.skills).toBe("Python, PyTorch");
    expect(v.experiences[0].tech).toBe("py");
    const back = toExtraction(v);
    expect(back.skills).toEqual(["Python", "PyTorch"]);
    expect(back.experiences?.[0]).toMatchObject({ company: "Acme", title: "ML Eng", tech: ["py"] });
  });

  it("drops empty scalars to undefined", () => {
    const back = toExtraction(toFormValues({ full_name: "", location: "Berlin" }));
    expect(back.full_name).toBeUndefined();
    expect(back.location).toBe("Berlin");
  });

  it("round-trips education and certification rows, and reports highlights next to tech", () => {
    const e = {
      experiences: [
        { company: "Acme", title: "ML Eng", highlights: ["shipped x", "cut p99"], tech: ["py"] },
      ],
      education: [
        {
          institution: "MIT",
          degree: "BSc",
          field: "CS",
          start_date: "2015",
          end_date: "2019",
          grade: "3.9",
        },
      ],
      certifications: [
        { name: "CKA", issuer: "CNCF", credential_id: "abc-123", url: "https://verify.example/abc" },
      ],
    };
    const v = toFormValues(e);
    // highlights are newline-delimited (one bullet per line), not CSV
    expect(v.experiences[0].highlights).toBe("shipped x\ncut p99");
    expect(v.education[0].institution).toBe("MIT");

    const back = toExtraction(v);
    expect(back.experiences?.[0]?.highlights).toEqual(["shipped x", "cut p99"]);
    expect(back.education?.[0]).toMatchObject({
      institution: "MIT",
      degree: "BSc",
      field: "CS",
      start_date: "2015",
      end_date: "2019",
      grade: "3.9",
    });
    expect(back.certifications?.[0]).toMatchObject({
      name: "CKA",
      issuer: "CNCF",
      credential_id: "abc-123",
      url: "https://verify.example/abc",
    });
  });

  it("keeps a comma inside a highlight bullet intact (no CSV shredding)", () => {
    const e = {
      experiences: [
        {
          company: "Acme",
          title: "ML Eng",
          highlights: ["Cut p99 latency by 40%, saving $120k/yr", "Shipped v2"],
        },
      ],
      projects: [
        { name: "mana", highlights: ["Built X, Y, and Z from scratch"] },
      ],
    };
    const v = toFormValues(e);
    expect(v.experiences[0].highlights).toBe(
      "Cut p99 latency by 40%, saving $120k/yr\nShipped v2",
    );

    const back = toExtraction(v);
    expect(back.experiences?.[0]?.highlights).toEqual([
      "Cut p99 latency by 40%, saving $120k/yr",
      "Shipped v2",
    ]);
    expect(back.projects?.[0]?.highlights).toEqual([
      "Built X, Y, and Z from scratch",
    ]);
  });

  it("treats a whitespace-only scalar as empty", () => {
    const back = toExtraction(
      toFormValues({ full_name: "  ", summary: " \t \n ", location: "Berlin" }),
    );
    expect(back.full_name).toBeUndefined();
    expect(back.summary).toBeUndefined();
    expect(back.location).toBe("Berlin");
  });

  it("keeps experience is_current through a converter round-trip with no control for it", () => {
    const v = toFormValues({
      experiences: [{ company: "Acme", title: "ML Eng", is_current: true }],
    });
    expect(v.experiences[0].is_current).toBe(true);

    const back = toExtraction(v);
    expect(back.experiences?.[0]?.is_current).toBe(true);
  });
});
