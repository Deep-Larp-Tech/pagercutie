import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-2 p-8">
      <h1 className="text-[24px]/[32px] font-semibold tracking-[-0.02em]">PagerCutie</h1>
      <p className="text-muted-foreground">Screens arrive in the next chunks.</p>
    </main>
  )
}
