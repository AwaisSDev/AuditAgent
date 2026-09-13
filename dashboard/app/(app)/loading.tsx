import { Skeleton } from "@/components/ui/skeleton";

// Next.js shows this automatically (wraps the route segment in a Suspense
// boundary) the instant a navigation starts, before the target route's own
// data even begins loading. Without it, a slow network leaves the *previous*
// page frozen on screen with zero feedback until the new route is fully
// ready — found by simulating a ~2.5s network delay and clicking between
// sidebar links: the old page just sat there, unchanged, looking hung.
export default function AppLoading() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-7 w-40" />
      <div className="space-y-3">
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    </div>
  );
}
