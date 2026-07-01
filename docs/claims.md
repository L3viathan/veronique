# Claims

A claim can be thought of as a simple sentence: It (normally) has a subject, a
verb, and an object. For example, "John loves Mary", "Peter is 28 years old",
or "Paul knows that [John loves Mary]".

A subject is either another claim, or NULL. The latter is only possible when
the verb is a special builtin one called `ROOT`. Root claims have no subject
and have their name as their object. They represent any kind of entity.

Now that we bootstrapped the world with root claims, we can talk about other
types of claims: They (non-root claims) always have a subject claim (which can
be, but doesn't have to be a root claim), a verb, and an object. The object can
either be another claim (when the verb has the data type `directed_link` or
`undirected_link`) or some atomic value (e.g. a number, a string, a date, ...).


TODO: How to create/edit a claim
