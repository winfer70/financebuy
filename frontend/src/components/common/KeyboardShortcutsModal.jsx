/**
 * KeyboardShortcutsModal
 *
 * Overlay modal that lists all registered keyboard shortcuts grouped by category.
 * Closes on Escape key or backdrop click.  Renders nothing when `isOpen` is false
 * so callers do not need to conditionally mount it.
 */

import React, { useEffect } from 'react';

/**
 * KeyboardShortcutsModal: Display registered shortcuts in a categorised table
 *
 * @param {boolean}  isOpen     - Whether the modal is visible
 * @param {Function} onClose    - Callback to close the modal
 * @param {Array}    shortcuts  - Array of shortcut descriptors (same shape as
 *                                useKeyboardShortcuts expects), each optionally
 *                                containing `category` and `description` fields
 * @returns {JSX.Element|null}
 */
const KeyboardShortcutsModal = ({ isOpen, onClose, shortcuts = [] }) => {
  /* Close on Escape when the modal is open */
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  /* Derive unique category names in insertion order */
  const categories = [...new Set(shortcuts.map(s => s.category || 'General'))];

  /**
   * formatKey: Render a key or key-sequence as styled chips
   *
   * @param {string|string[]} key - Single key string or two-element sequence array
   * @returns {JSX.Element|JSX.Element[]}
   */
  const formatKey = (key) => {
    if (Array.isArray(key)) {
      /* Sequence shortcut — render each key separated by an arrow indicator */
      return key
        .map(k => <span key={k} className="shortcut-key">{k.toUpperCase()}</span>)
        .reduce((acc, el, i) =>
          i === 0
            ? [el]
            : [...acc, <span key={`sep-${i}`} style={{ margin: '0 4px', opacity: 0.5 }}>→</span>, el],
          []
        );
    }
    return <span className="shortcut-key">{key === '?' ? '?' : key.toUpperCase()}</span>;
  };

  return (
    /* Backdrop — click to close */
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-box"
        onClick={e => e.stopPropagation()}
        style={{ maxWidth: '480px', width: '90%' }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--amber, #f59e0b)' }}>
            KEYBOARD SHORTCUTS
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--muted, #888)', cursor: 'pointer', fontSize: '16px' }}
          >
            ×
          </button>
        </div>

        {/* Shortcut groups */}
        {categories.map(cat => (
          <div key={cat} style={{ marginBottom: '16px' }}>
            {/* Category label */}
            <div style={{
              fontSize: '10px', color: 'var(--muted, #888)',
              textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '1px'
            }}>
              {cat}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody>
                {shortcuts
                  .filter(s => (s.category || 'General') === cat)
                  .map((s, i) => (
                    <tr key={i}>
                      <td style={{ padding: '4px 0', fontSize: '11px', color: 'var(--text, #ccc)', width: '60%' }}>
                        {s.description}
                      </td>
                      <td style={{ padding: '4px 0', textAlign: 'right' }}>
                        {formatKey(s.key)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
};

export default KeyboardShortcutsModal;
export { KeyboardShortcutsModal };
