export const metadata = {
  title: "For maintainers",
  description: "What FirstPR does with your repo, how it keeps newcomers from bothering you, and how to opt out.",
};

const RULES: [string, string][] = [
  ["Only free issues", "FirstPR suggests issues with no assignee, no linked pull request and no recent claim in the comments, and checks again just before someone starts."],
  ["One person at a time", "An issue is held for one person while they work on it, so you do not get five pull requests for the same issue."],
  ["Your rules first", "People see a checklist before they start: read CONTRIBUTING, ask on the issue the way your repo expects, sign the CLA or DCO, one issue per pull request."],
  ["A practice run first", "A person's first pull request goes to a practice repo, not to you."],
  ["A limit on open pull requests", "Nobody can have more than three open pull requests waiting for review."],
  ["Nothing automatic", "FirstPR never comments, opens issues or opens pull requests on its own. Every pull request is opened by a person, with their own account."],
];

export default function MaintainersPage() {
  return (
    <main className="flex flex-col gap-6 py-6">
      <div>
        <h1 className="text-3xl font-bold">For maintainers</h1>
        <p className="max-w-[65ch] text-ink-2">
          FirstPR helps people make their first contributions to open source. It only reads public
          data from your repo, and it tries hard to send you careful, prepared contributors, not
          more work.
        </p>
      </div>
      <section className="grid gap-3 md:grid-cols-2">
        {RULES.map(([title, text]) => (
          <div key={title} className="rounded-lg border border-line bg-surface p-5">
            <h2 className="mb-1 font-semibold">{title}</h2>
            <p className="text-sm text-ink-2">{text}</p>
          </div>
        ))}
      </section>
      <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5">
        <h2 className="text-xl font-semibold">Opt out</h2>
        <p className="text-ink-2">
          Add this file to your repo&apos;s default branch. Within a day FirstPR stops suggesting
          your issues, removes them from its pages and stops reading your repo. Delete the file to
          come back.
        </p>
        <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 text-sm">
          <code>{"# .github/firstpr.yml\nopt_out: true\n"}</code>
        </pre>
        <p className="text-sm text-ink-2">
          Questions or problems? <a href="/feedback" className="underline">Tell us</a>.
        </p>
      </section>
    </main>
  );
}
