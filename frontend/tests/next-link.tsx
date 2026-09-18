/** Browser-style link used only by component tests; production uses the router. */
import type { AnchorHTMLAttributes } from "react";

export default function Link({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <a href={href} {...props}>{children}</a>;
}
