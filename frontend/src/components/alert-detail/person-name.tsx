import type { PersonName } from '@/hooks/use-person-name'

/** A user as `usePersonName` resolved them: "You", their name, or a short id in Geist Mono with the full id on hover. */
export function PersonNameText({ person }: { person: PersonName }) {
  switch (person.kind) {
    case 'me':
      return <>You</>
    case 'name':
      return <>{person.name}</>
    case 'id':
      return (
        <span className="font-mono" title={person.id}>
          User {person.shortId}
        </span>
      )
    default:
      return person satisfies never
  }
}
