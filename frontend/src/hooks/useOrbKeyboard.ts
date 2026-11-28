import { useEffect, useRef } from "react";
import type { OrbController } from "../orb/orbController";

/**
 * Keyboard controls for the orb:
 *   arrow keys rotate, + / - resize, P pauses/resumes rotation, 0 resets, Esc cancels.
 * Ignored while typing in a text field.
 */
export function useOrbKeyboard(controller: OrbController, onCancel: () => void): void {
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    const STEP = 0.18;
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;

      let handled = true;
      switch (event.key) {
        case "ArrowLeft":
          controller.rotateBy(-STEP, 0);
          break;
        case "ArrowRight":
          controller.rotateBy(STEP, 0);
          break;
        case "ArrowUp":
          controller.rotateBy(0, -STEP);
          break;
        case "ArrowDown":
          controller.rotateBy(0, STEP);
          break;
        case "+":
        case "=":
          controller.zoomBy(1.1);
          break;
        case "-":
        case "_":
          controller.zoomBy(1 / 1.1);
          break;
        case "p":
        case "P":
          controller.togglePaused();
          break;
        case "0":
          controller.reset();
          break;
        case "Escape":
          cancelRef.current();
          break;
        default:
          handled = false;
      }
      if (handled) event.preventDefault();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [controller]);
}
