import { contactSchema } from "@/components/site/forms";
import { registerSchema } from "@/lib/schemas";

describe("registerSchema", () => {
  const valid = { full_name: "Ada Lovelace", email: "ada@example.com", password: "Analytical-1", organisation_name: "Engines Ltd" };
  it("accepts a valid registration", () => expect(registerSchema.safeParse(valid).success).toBe(true));
  it("enforces the password policy mirrored from the API", () => {
    for (const password of ["short1", "nodigitsatall", "1234567890"]) {
      expect(registerSchema.safeParse({ ...valid, password }).success).toBe(false);
    }
  });
  it("requires a valid email and organisation", () => {
    expect(registerSchema.safeParse({ ...valid, email: "nope" }).success).toBe(false);
    expect(registerSchema.safeParse({ ...valid, organisation_name: " " }).success).toBe(false);
  });
});

describe("contactSchema", () => {
  it("rejects missing required fields with helpful messages", () => {
    const r = contactSchema.safeParse({ full_name: "", email: "x", company: "", topic: "" });
    expect(r.success).toBe(false);
    const messages = r.success ? [] : r.error.issues.map((i) => i.message);
    expect(messages).toContain("Please enter your name");
    expect(messages).toContain("Enter a valid work email");
  });
});
