import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase-browser", () => ({
  createSupabaseBrowserClient: vi.fn(),
}));

import { createSupabaseBrowserClient } from "@/lib/supabase-browser";
import { api } from "@/lib/api";

function mockSession(accessToken: string | null) {
  (createSupabaseBrowserClient as ReturnType<typeof vi.fn>).mockReturnValue({
    auth: {
      getSession: () =>
        Promise.resolve({
          data: { session: accessToken ? { access_token: accessToken } : null },
        }),
    },
  });
}

function mockFetch(response: Partial<Response> & { status: number }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: response.status >= 200 && response.status < 300,
    status: response.status,
    statusText: response.statusText ?? "",
    text: response.text ?? (() => Promise.resolve("")),
    json: response.json ?? (() => Promise.resolve(undefined)),
    blob: response.blob ?? (() => Promise.resolve(new Blob())),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("api requests", () => {
  it("attaches the session's bearer token when one exists", async () => {
    mockSession("token-123");
    const fetchMock = mockFetch({ status: 200, json: () => Promise.resolve({ ok: true }) });

    await api.get("/v1/workspaces");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/v1/workspaces");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-123");
  });

  it("sends no Authorization header when there is no session", async () => {
    mockSession(null);
    const fetchMock = mockFetch({ status: 200, json: () => Promise.resolve({}) });

    await api.get("/v1/workspaces");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("sets Content-Type: application/json for a JSON body", async () => {
    mockSession("t");
    const fetchMock = mockFetch({ status: 201, json: () => Promise.resolve({ id: "1" }) });

    await api.post("/v1/agents", { name: "bot" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "bot" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("omits Content-Type for a FormData body (postForm)", async () => {
    mockSession("t");
    const fetchMock = mockFetch({ status: 201, json: () => Promise.resolve({ id: "1" }) });
    const form = new FormData();
    form.append("file", new Blob(["x"]), "x.csv");

    await api.postForm("/v1/questionnaires", form);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBe(form);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("omits Content-Type for a bodyless request", async () => {
    mockSession("t");
    const fetchMock = mockFetch({ status: 200, json: () => Promise.resolve([]) });

    await api.get("/v1/workspaces");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("returns undefined for a 204 No Content response without calling .json()", async () => {
    mockSession("t");
    const jsonSpy = vi.fn();
    mockFetch({ status: 204, json: jsonSpy });

    const result = await api.delete("/v1/api-keys/key-1");

    expect(result).toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it("throws an Error including status and body text on a non-ok response", async () => {
    mockSession("t");
    mockFetch({ status: 402, statusText: "Payment Required", text: () => Promise.resolve("Plan limit reached") });

    await expect(api.post("/v1/agents", { name: "bot" })).rejects.toThrow(/402 Payment Required: Plan limit reached/);
  });

  it("uses PATCH/PUT with the expected method and JSON body", async () => {
    mockSession("t");
    const fetchMock = mockFetch({ status: 200, json: () => Promise.resolve({}) });

    await api.patch("/v1/answers/a1", { status: "approved" });
    await api.put("/v1/workspaces/ws-1/policy", { rules_yaml: "rules: []" });

    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(fetchMock.mock.calls[1][1].method).toBe("PUT");
  });
});

// downloadFile() is DOM-dependent (document.createElement, URL.createObjectURL)
// and this suite deliberately runs in a plain Node environment (no jsdom) to
// keep the pure-logic modules fast and dependency-light — it's covered
// instead by this session's live browser verification of CSV export.
