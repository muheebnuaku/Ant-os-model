import { Badge, PageHeader, Section } from "@/components/ui";

const RESULTS = [
  ["trusted", "The evidence is strong and consistent. Decisions may be cleared to act."],
  ["provisional", "Reasonable evidence that should be confirmed by an independent source."],
  ["decayed", "The evidence is too old. Refresh it from the source."],
  ["conflicted", "Sources disagree. Resolve the disagreement before acting."],
  ["blocked", "The evidence is unsafe to act on. A person is always called."],
] as const;

export default function HelpPage() {
  return (
    <div className="page content-narrow">
      <PageHeader title="Help" description="How to read ANT-OS." />
      <Section title="What ANT-OS does">
        <div className="card card-pad stack-sm">
          <p>ANT-OS receives evidence from institutions, data feeds and communities, checks how far it can be trusted, and advises an action. When the evidence is weak, contradictory, or the decision affects workers, communities or national data, it calls a person instead of acting.</p>
          <p>Every step is written to a permanent record that is sealed daily. Any decision can be re-run from that record to prove it has not been changed.</p>
        </div>
      </Section>
      <Section title="Evidence results">
        <div className="card">
          <table className="table">
            <caption className="sr-only">Evidence results</caption>
            <thead><tr><th>Result</th><th>Meaning</th></tr></thead>
            <tbody>
              {RESULTS.map(([s, t]) => <tr key={s}><td data-label="Result"><Badge status={s} /></td><td data-label="Meaning">{t}</td></tr>)}
            </tbody>
          </table>
        </div>
      </Section>
      <Section title="Reviews">
        <div className="card card-pad stack-sm">
          <p>A review is a decision waiting for a person. Each has a priority and a deadline. Acknowledge a review when you pick it up, and resolve it with a note explaining what was decided. The note becomes part of the permanent record.</p>
        </div>
      </Section>
      <Section title="Keyboard shortcuts">
        <div className="card">
          <table className="table">
            <caption className="sr-only">Keyboard shortcuts</caption>
            <thead><tr><th>Keys</th><th>Action</th></tr></thead>
            <tbody>
              {[
                ["Ctrl K", "Search decisions, sectors and pages"],
                ["G then B", "Go to Briefing"],
                ["G then R", "Go to Review queue"],
                ["G then D", "Go to Decisions"],
                ["G then N", "Start a new decision"],
                ["G then S", "Go to Signals"],
                ["G then A", "Go to Records & verification"],
                ["Esc", "Close a panel, dialog or menu"],
              ].map(([k, a]) => <tr key={k}><td data-label="Keys"><kbd style={{ marginLeft: 0 }}>{k}</kbd></td><td data-label="Action">{a}</td></tr>)}
            </tbody>
          </table>
        </div>
      </Section>
      <Section title="Not assessed and No data">
        <div className="card card-pad"><p>ANT-OS never fills gaps. When a check could not be made, it says “Not assessed”. When nothing was reported, it says “No data”.</p></div>
      </Section>
    </div>
  );
}
