"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { DecisionsConsole } from "@/components/DecisionsConsole";

export default function DecisionsPage() {
  return <Suspense fallback={null}><Decisions /></Suspense>;
}

function Decisions() {
  return <DecisionsConsole selected={useSearchParams().get("ref")} />;
}
