import { api, ApiError, errorMessage, setAccessToken } from "@/lib/api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => { vi.restoreAllMocks(); setAccessToken(null); });

describe("api client", () => {
  it("sends the bearer token and parses JSON", async () => {
    setAccessToken("tok");
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { ok: true }));
    await expect(api("/things")).resolves.toEqual({ ok: true });
    const headers = f.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok");
  });

  it("refreshes once on 401 and retries the request", async () => {
    setAccessToken("expired");
    const f = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(401, { error: { code: "unauthorized", message: "expired" } }))
      .mockResolvedValueOnce(json(200, { access_token: "fresh" }))
      .mockResolvedValueOnce(json(200, { id: 1 }));
    await expect(api("/secure")).resolves.toEqual({ id: 1 });
    expect(f.mock.calls[1][0]).toBe("/api/v1/auth/refresh");
    expect((f.mock.calls[2][1]!.headers as Headers).get("Authorization")).toBe("Bearer fresh");
  });

  it("surfaces the API error envelope as ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(409, { error: { code: "invalid_transition", message: "Nope", details: { allowed: ["draft"] }, request_id: "r1" } }));
    const err = await api("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("invalid_transition");
    expect(errorMessage(err)).toBe("Nope (allowed: draft)");
  });

  it("formats validation errors field by field", () => {
    const e = new ApiError(422, "validation_error", "Request validation failed", [{ loc: ["body", "email"], msg: "invalid email" }]);
    expect(errorMessage(e)).toBe("email: invalid email");
  });

  it("sends the Idempotency-Key header when provided", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, {}));
    await api("/submit", { method: "POST", idempotencyKey: "k-1" });
    expect((f.mock.calls[0][1]!.headers as Headers).get("Idempotency-Key")).toBe("k-1");
  });
});
