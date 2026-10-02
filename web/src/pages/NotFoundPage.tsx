import { Link } from "react-router";

import { EmptyState } from "@/components/ui/states";

export function NotFoundPage() {
  return (
    <EmptyState title="There's no page here">
      Head back to the <Link to="/">radar</Link>.
    </EmptyState>
  );
}
