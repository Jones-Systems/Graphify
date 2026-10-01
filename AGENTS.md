# Graphify agent guidance

Graphify owns graph production, validation, portable snapshot access, and the
instructions for consumers. Populated graph stores stay outside source Git.

For graph navigation or distributing selected snapshots to repository agents,
load [.agents/skills/graphify-query/SKILL.md](.agents/skills/graphify-query/SKILL.md).
Use its CLI selectively, then confirm claims in current source. Reader access
does not authorize rebuilding, promoting, transferring to another host, or
changing shared runtime bindings.

The portable catalog reader and the older promoted-corpus tooling are separate
interfaces. Preserve both until an explicit custody or migration decision.
