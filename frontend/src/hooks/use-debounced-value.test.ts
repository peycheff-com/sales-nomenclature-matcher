import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "./use-debounced-value";

afterEach(() => {
  vi.useRealTimers();
});

describe("useDebouncedValue", () => {
  it("keeps the previous value until the delay elapses", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: "initial" } },
    );

    expect(result.current).toBe("initial");

    rerender({ value: "next" });
    expect(result.current).toBe("initial");

    act(() => {
      vi.advanceTimersByTime(249);
    });
    expect(result.current).toBe("initial");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("next");
  });

  it("cancels pending updates when the value changes again", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 100),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    rerender({ value: "c" });
    act(() => {
      vi.advanceTimersByTime(99);
    });

    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("c");
  });
});
