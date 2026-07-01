# Véronique

Véronique is a weird mix of address book, family tree software, and graphical
(in the sense of graph as in network, not drawing) notetaking app — at least
that's how its author uses it. Other usecases are possible, but may not be as
supported by special UI features as these ones. Since that's a little abstract,
instead here's a few tasks that you can do with Véronique:

- Be reminded about birthdays and other anniversaries
- Discover previously unknown connections (e.g., "Huh, I never knew my
  highschool deskmate _and_ my neighbour both worked at the same company!")
- Answer questions like:
    - "How many people that I know were born in 1970?"
    - "What are the oldest people I know?"
    - "Which couple in my ancestors had the largest age difference?"

As Véronique attempts to model (a fragment of) the real world, it can deal with
uncertanties in some places:

- There are no facts, there are [claims](claims.md).
- Claims can be restricted in their validity (e.g., "only valid until
  1992-05-13").
- Any date supports (partial) uncertainty: "2025-01-02" is a date, but so is
  "2025-??-??" (some time in 2025) or "????-04-09" (ninth of July some year).
- You can make claims about claims ("Peter believes [Judy works-at Acme]")
