import Link from "next/link";

export const metadata = { title: "Email turned off · FirstPR" };

export default async function EmailOffPage({
  searchParams,
}: {
  searchParams: Promise<{ bad?: string }>;
}) {
  const { bad } = await searchParams;
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-16">
      <h1 className="text-3xl font-bold">{bad ? "That link did not work" : "Email is off"}</h1>
      <p className="text-ink-2">
        {bad
          ? "The unsubscribe link is broken or old. Sign in and turn email off in Settings instead."
          : "FirstPR will not email you any more: no updates and no digest. You can turn it back on in Settings whenever you like."}
      </p>
      <Link href="/settings" className="self-start rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink">
        Open Settings
      </Link>
    </main>
  );
}
