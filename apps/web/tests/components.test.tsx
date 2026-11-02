import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { StatusBadge } from "@/components/app/common";
import { ContactForm } from "@/components/site/forms";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("topic=Knowledge%20assistant"), useRouter: () => ({ push: vi.fn() }) }));

afterEach(() => vi.restoreAllMocks());

describe("StatusBadge", () => {
  it("labels and colours statuses", () => {
    render(<StatusBadge status="awaiting_approval" />);
    const el = screen.getByText("Awaiting Approval");
    expect(el.className).toMatch(/warning/);
  });
});

describe("ContactForm", () => {
  it("shows validation errors and does not call the API when invalid", async () => {
    const f = vi.spyOn(globalThis, "fetch");
    render(<ContactForm kind="contact" />);
    await userEvent.click(await screen.findByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Please enter your name")).toBeInTheDocument();
    expect(f).not.toHaveBeenCalled();
  });

  it("pre-selects the topic from the URL and submits to the public API", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 201, headers: { "content-type": "application/json" } }));
    render(<ContactForm kind="contact" />);
    expect(await screen.findByLabelText("Topic")).toHaveValue("Knowledge assistant");
    await userEvent.type(screen.getByLabelText("Full name"), "Grace Hopper");
    await userEvent.type(screen.getByLabelText("Work email"), "grace@example.com");
    await userEvent.type(screen.getByLabelText("Company"), "Navy");
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Message sent")).toBeInTheDocument();
    expect(f.mock.calls[0][0]).toBe("/api/v1/public/discovery-calls");
    expect(JSON.parse(f.mock.calls[0][1]!.body as string)).toMatchObject({ kind: "contact", topic: "Knowledge assistant", company: "Navy" });
  });

  it("shows the server error when the API rejects the request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "rate_limited", message: "Too many requests, retry later" } }),
      { status: 429, headers: { "content-type": "application/json" } }));
    render(<ContactForm kind="contact" />);
    await userEvent.type(await screen.findByLabelText("Full name"), "Grace Hopper");
    await userEvent.type(screen.getByLabelText("Work email"), "grace@example.com");
    await userEvent.type(screen.getByLabelText("Company"), "Navy");
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests");
  });
});
