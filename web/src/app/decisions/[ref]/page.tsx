"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { DecisionsConsole } from "@/components/DecisionsConsole";

/* A direct link to one decision opens the console with it selected. */

export default function DecisionPage() {
  return <Suspense fallback={null}><Decision /></Suspense>;
}

function Decision() {
  const { ref } = useParams<{ ref: string }>();
  return <DecisionsConsole selected={decodeURIComponent(ref)} />;
}
