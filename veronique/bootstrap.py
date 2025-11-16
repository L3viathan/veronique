import sys
import os

def make(name, *relations, category="human"):
    person = O.Claim.new_root(name)
    O.Claim.new(person, O.Verb(veronique.db.IS_A), categories[category])
    for verb, obj in relations:
        if not isinstance(obj, O.Claim):
            obj = O.Plain(obj, verb)
        O.Claim.new(person, verb, obj)
    return person


if __name__ == "__main__":
    if os.path.exists("veronique.db"):
        print(
            "Can't bootstrap, DB already exists. Delete veronique.db and run this again.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open("veronique_initial_pw", "w") as f:
        f.write("admin")
    # running migrations:
    import veronique.db  # noqa
    import veronique.objects as O
    from veronique.context import context
    context.user = O.User(0)
    categories = {}
    for category in ["human", "place", "event", "company"]:
        categories[category] = O.Claim.new_root(category)
    child_of = O.Verb.new("child of", data_type=O.TYPES["directed_link"])
    birthdate = O.Verb.new("birth date", data_type=O.TYPES["date"])
    partner_of = O.Verb.new("partner of", data_type=O.TYPES["undirected_link"])
    O.Verb.new(
        "sibling of",
        data_type=O.TYPES["inferred"],
        extra=f'{{"g1s": "this", "g1v": "{child_of.id}", "g1o": "A","g2s": "that", "g2v": "{child_of.id}", "g2o": "A"}}',
    )
    works_at = O.Verb.new("works at", data_type=O.TYPES["directed_link"])

    snpp = make("Springfield Nuclear Power Plant", category="company")
    abe = make("Abraham Simpson", (birthdate, "1901-05-25"))
    mona = make("Mona Penelope Olsen", (birthdate, "1923-03-15"), (partner_of, abe))
    make("Herb Powell", (child_of, abe))
    homer = make(
        "Homer Simpson",
        (child_of, abe),
        (child_of, mona),
        (birthdate, "1956-05-12"),
        (works_at, snpp),
    )
    clancy = make("Clancy Bouvier")
    jacqueline = make("Jacqueline Ingrid Bouvier")
    marge = make(
        "Marge Bouvier",
        (child_of, clancy),
        (child_of, jacqueline),
        (birthdate, "1955-03-19"),
        (partner_of, homer),
    )
    make(
        "Patty Bouvier",
        (child_of, clancy),
        (child_of, jacqueline),
        (birthdate, "1948-??-??"),
    )
    make(
        "Selma Bouvier",
        (child_of, clancy),
        (child_of, jacqueline),
        (birthdate, "1948-??-??"),
    )
    make(
        "Bart Simpson",
        (child_of, homer),
        (child_of, marge),
        (birthdate, "1979-02-23"),
    )
    make("Lisa Simpson", (child_of, homer), (child_of, marge), (birthdate, "1981-05-09"))
    make("Maggie Simpson", (child_of, homer), (child_of, marge), (birthdate, "1988-01-14"))
    make("Ned Flanders", (birthdate, "1929-??-??"))
    make("Lenny Leonard", (birthdate, "1950-04-13"), (works_at, snpp))
    make("Carl Carlson", (birthdate, "1950-04-20"), (works_at, snpp))
    make("Barney Gumble", (birthdate, "1949-04-20"))
    make("Otto Mann", (birthdate, "1960-01-18"))
    make("Comic Book Guy", (birthdate, "1954-??-??"))
    wiggum = make("Clancy Wiggum", (birthdate, "1946-04-28"))
    make("Ralph Wiggum", (child_of, wiggum))
    make("Charles Montgomery Burns", (birthdate, "1900-09-15"), (works_at, snpp))
    make("Herschel \"Krusty\" Krustofski", (birthdate, "1941-06-15"))
    make("Moe Szyslak", (birthdate, "1948-11-24"))
    make("Jimbo Jones", (birthdate, "1973-10-26"))
    make("Kearney Zzyzwicz", (birthdate, "1960-10-09"))
    make("Dolph Starbeam", (birthdate, "1975-10-01"))
    reverend = make("Timothy Lovejoy", (birthdate, "1952-??-??"))
    make("Helen Lovejoy", (birthdate, "1954-??-??"), (partner_of, reverend))
    make("Jasper Beadly", (birthdate, "1899-10-25"))
    make("Hans Moleman", (birthdate, "1958-08-02"))
    apu = make("Apu Nahasapeemapetilon", (birthdate, "1951-??-??"))
    make("Manjula Nahasapeemapetilon", (birthdate, "1958-??-??"), (partner_of, apu))
    make("Seymour Skinner", (birthdate, "1943-11-01"))
    make("Joe Quimby", (birthdate, "1945-??-??"))
    make("Nelson Muntz", (birthdate, "1979-10-30"))
    make("Waylon Smithers", (birthdate, "1953-12-25"), (works_at, snpp))
