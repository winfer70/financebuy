/**
 * useKeyboardShortcuts
 *
 * Global keyboard shortcut handler for the TickerTap application.
 * Registers a document-level keydown listener and dispatches to the
 * matching shortcut action.
 *
 * Features:
 * - Skips handler when focus is inside an INPUT, TEXTAREA, or SELECT element.
 * - Supports single-key shortcuts (e.g. { key: '/', action: openSearch }).
 * - Supports two-key sequence shortcuts (e.g. { key: ['g','d'], action: goToDashboard })
 *   with a 1 500 ms window between the two key presses.
 * - Exposes `pendingSequence` so the UI can show a "waiting for second key" hint.
 *
 * @module useKeyboardShortcuts
 */

import { useEffect, useRef, useState } from 'react';

/** HTML tags that indicate the user is typing; shortcuts should be suppressed */
const INPUT_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

/**
 * useKeyboardShortcuts: Bind global keyboard shortcuts
 *
 * @param {Array<{key: string|string[], action: Function, category?: string, description?: string}>} shortcuts
 *   Array of shortcut descriptors. `key` is either a single key string or a
 *   two-element array for sequence shortcuts.
 * @returns {{ pendingSequence: string|null }}
 *   `pendingSequence` is the first key of an in-progress sequence, or null.
 */
export default function useKeyboardShortcuts(shortcuts) {
  const [pendingSequence, setPendingSequence] = useState(null);

  /* Refs allow the timeout callback to read/write state without stale closure issues */
  const pendingRef = useRef(null);
  const timeoutRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      /* Skip shortcuts when user is typing in a form field */
      if (INPUT_TAGS.has(e.target.tagName)) return;
      const key = e.key.toLowerCase();

      /* ── Sequence second-key handling ── */
      if (pendingRef.current) {
        clearTimeout(timeoutRef.current);

        /* Find a sequence shortcut whose first key matches what we buffered */
        const seq = shortcuts.find(s =>
          Array.isArray(s.key) && s.key[0] === pendingRef.current && s.key[1] === key
        );
        pendingRef.current = null;
        setPendingSequence(null);

        if (seq) {
          e.preventDefault();
          seq.action();
        }
        return;
      }

      /* ── Single-key shortcut ── */
      const single = shortcuts.find(s => !Array.isArray(s.key) && s.key === key);
      if (single) {
        e.preventDefault();
        single.action();
        return;
      }

      /* ── Sequence first-key buffering ── */
      const seqStart = shortcuts.find(s => Array.isArray(s.key) && s.key[0] === key);
      if (seqStart) {
        pendingRef.current = key;
        setPendingSequence(key);

        /* Clear pending sequence after 1 500 ms if no second key arrives */
        timeoutRef.current = setTimeout(() => {
          pendingRef.current = null;
          setPendingSequence(null);
        }, 1500);
      }
    };

    document.addEventListener('keydown', handler);

    return () => {
      document.removeEventListener('keydown', handler);
      clearTimeout(timeoutRef.current);
    };
  }, [shortcuts]);

  return { pendingSequence };
}
