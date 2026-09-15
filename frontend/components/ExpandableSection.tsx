"use client";

/** Accessible disclosure panel that defers expensive child rendering until opened. */

import { ReactNode, useState } from "react";

type ExpandableSectionProps = {
  title: string;
  description: string;
  badge?: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

export function ExpandableSection({ title, description, badge, defaultOpen = false, children }: ExpandableSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const panelId = `panel-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <section className={`expandable-section${isOpen ? " is-open" : ""}`}>
      <button
        className="expandable-trigger"
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((value) => !value)}
      >
        <span><strong>{title}</strong><small>{description}</small></span>
        <span className="expandable-actions">{badge && <em>{badge}</em>}<span className="dropdown-arrow" aria-hidden="true">⌄</span></span>
      </button>
      {isOpen && <div className="expandable-content" id={panelId}>{children}</div>}
    </section>
  );
}
