import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, BACKEND_UNREACHABLE_MESSAGE, isUnreachableStatus } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isUnreachableStatus", () => {
  it("treats proxy/gateway statuses as 'backend never answered'", () => {
    expect(isUnreachableStatus(502)).toBe(true);
    expect(isUnreachableStatus(503)).toBe(true);
    expect(isUnreachableStatus(504)).toBe(true);
  });

  it("does not swallow real application errors", () => {
    expect(isUnreachableStatus(500)).toBe(false);
    expect(isUnreachableStatus(401)).toBe(false);
    expect(isUnreachableStatus(422)).toBe(false);
    expect(isUnreachableStatus(200)).toBe(false);
  });
});

describe("ApiError", () => {
  it("exposes the backend-unreachable flag", () => {
    const error = new ApiError(BACKEND_UNREACHABLE_MESSAGE, "backend_unreachable", 502);
    expect(error.isBackendUnreachable).toBe(true);
    expect(error.message).toContain("后端");
  });

  it("keeps the other classifications", () => {
    expect(new ApiError("x", "auth_required", 401).isAuthError).toBe(true);
    expect(new ApiError("x", "not_found", 404).isNotFound).toBe(true);
    expect(new ApiError("x", "conflict", 409).isConflict).toBe(true);
    expect(new ApiError("x", "provider_error", 502).isBackendUnreachable).toBe(false);
  });
});