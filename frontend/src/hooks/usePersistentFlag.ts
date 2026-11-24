import { useCallback, useState } from "react";

/** A boolean preference remembered in localStorage. */
export function usePersistentFlag(key: string, initial = false): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initial : stored === "1";
    } catch {
      return initial;
    }
  });

  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* storage unavailable (private mode): the choice just lasts for this session */
      }
    },
    [key]
  );

  return [value, update];
}
