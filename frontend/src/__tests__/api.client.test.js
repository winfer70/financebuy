/**
 * ============================================================================
 * TEST SUITE: API Client
 * ============================================================================
 *
 * MODULE UNDER TEST: src/api/client.js
 * TEST TYPE: Unit
 * FRAMEWORK: Vitest
 *
 * DESCRIPTION:
 *   Tests the apiFetch wrapper and the api object for correct HTTP behaviour,
 *   error handling, 401 session-expiry events, and the useApi hook's
 *   loading/error/data state transitions.
 *
 * COVERAGE SCOPE:
 *   ✓ apiFetch — successful GET, successful POST with body
 *   ✓ apiFetch — non-ok response throws Error with server detail
 *   ✓ apiFetch — 401 with token dispatches 'session-expired' event
 *   ✓ apiFetch — 401 without token does NOT dispatch event
 *   ✓ useApi hook — loading state, success state, error state, refetch
 *
 * EXECUTION REQUIREMENTS:
 *   - Run inside Vitest with jsdom environment
 *   - npm test
 * ============================================================================
 */

import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { apiFetch, useApi } from "../api/client";

// ── Global fetch mock ────────────────────────────────────────────────────────
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
});

/**
 * Helper — build a mock Response that fetch() will resolve with.
 *
 * @param {any}    body       - JSON-serialisable response body
 * @param {number} [status=200]
 */
function mockFetchResponse(body, status = 200) {
  const ok = status >= 200 && status < 300;
  fetch.mockResolvedValueOnce({
    ok,
    status,
    json: () => Promise.resolve(body),
    statusText: ok ? "OK" : "Error",
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// SUITE 1: apiFetch
// ═══════════════════════════════════════════════════════════════════════════

describe("apiFetch", () => {
  // ── Happy path ─────────────────────────────────────────────────────────

  test("should return parsed JSON for a successful GET request", async () => {
    // ARRANGE
    const expected = { status: "ok" };
    mockFetchResponse(expected, 200);

    // ACT
    const result = await apiFetch("/health");

    // ASSERT
    expect(result).toEqual(expected);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/health"),
      expect.objectContaining({ method: "GET" })
    );
  });

  test("should send JSON body for POST requests", async () => {
    // ARRANGE
    mockFetchResponse({ access_token: "tok" }, 200);
    const body = { email: "a@b.com", password: "pass" };

    // ACT
    await apiFetch("/auth/login", { method: "POST", body });

    // ASSERT
    const [, opts] = fetch.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual(body);
  });

  test("should include Authorization header when token is provided", async () => {
    // ARRANGE
    mockFetchResponse({}, 200);
    const token = "my-jwt-token";

    // ACT
    await apiFetch("/protected", { token });

    // ASSERT
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers["Authorization"]).toBe(`Bearer ${token}`);
  });

  test("should NOT include Authorization header when token is absent", async () => {
    // ARRANGE
    mockFetchResponse({}, 200);

    // ACT
    await apiFetch("/health");

    // ASSERT
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers["Authorization"]).toBeUndefined();
  });

  // ── Error handling ──────────────────────────────────────────────────────

  test("should throw an Error with server detail on non-ok response", async () => {
    // ARRANGE
    mockFetchResponse({ detail: "invalid credentials" }, 401);
    // No token → won't dispatch session-expired, will just throw

    // ACT & ASSERT
    await expect(apiFetch("/auth/login")).rejects.toThrow("invalid credentials");
  });

  test("should throw an Error with HTTP status when body has no detail", async () => {
    // ARRANGE
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
      statusText: "Internal Server Error",
    });

    // ACT & ASSERT
    await expect(apiFetch("/broken")).rejects.toThrow("Internal Server Error");
  });

  // ── 401 session-expiry event ────────────────────────────────────────────

  test("should dispatch 'session-expired' event on 401 when token is present", async () => {
    // ARRANGE
    mockFetchResponse({ detail: "expired" }, 401);
    const listener = vi.fn();
    window.addEventListener("session-expired", listener);

    // ACT & ASSERT
    await expect(apiFetch("/api/data", { token: "tok" })).rejects.toThrow("Session expired");
    expect(listener).toHaveBeenCalledOnce();

    window.removeEventListener("session-expired", listener);
  });

  test("should NOT dispatch session-expired on 401 without token", async () => {
    // ARRANGE
    mockFetchResponse({ detail: "unauthorized" }, 401);
    const listener = vi.fn();
    window.addEventListener("session-expired", listener);

    // ACT
    await expect(apiFetch("/open-endpoint")).rejects.toThrow();
    expect(listener).not.toHaveBeenCalled();

    window.removeEventListener("session-expired", listener);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// SUITE 2: useApi hook
// ═══════════════════════════════════════════════════════════════════════════

describe("useApi hook", () => {
  test("should start in loading state", async () => {
    // ARRANGE — fetcher never resolves during this check
    const fetcher = () => new Promise(() => {}); // pending forever

    // ACT
    const { result } = renderHook(() => useApi(fetcher));

    // ASSERT — on mount, loading should be true
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  test("should set data and clear loading on success", async () => {
    // ARRANGE
    const expected = { holdings: [] };
    const fetcher  = vi.fn().mockResolvedValue(expected);

    // ACT
    const { result } = renderHook(() => useApi(fetcher));

    // ASSERT — wait for async resolution
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual(expected);
    expect(result.current.error).toBeNull();
  });

  test("should set error message and clear loading on failure", async () => {
    // ARRANGE
    const fetcher = vi.fn().mockRejectedValue(new Error("Network error"));

    // ACT
    const { result } = renderHook(() => useApi(fetcher));

    // ASSERT
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("Network error");
    expect(result.current.data).toBeNull();
  });

  test("refetch should re-invoke fetcher and update data", async () => {
    // ARRANGE
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ count: 1 })
      .mockResolvedValueOnce({ count: 2 });

    // ACT — initial render
    const { result } = renderHook(() => useApi(fetcher));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ count: 1 });

    // ACT — explicit refetch
    act(() => { result.current.refetch(); });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // ASSERT
    expect(result.current.data).toEqual({ count: 2 });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
