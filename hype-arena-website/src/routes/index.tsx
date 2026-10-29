import { createFileRoute, redirect } from "@tanstack/react-router";

// The data-explorer pages are gone; the site starts on the architecture walkthrough.
export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/how-it-works" });
  },
});
