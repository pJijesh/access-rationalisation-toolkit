# Limitations and responsible use

`access-rat` is an analysis aid. It produces a proposal and the evidence for reviewing it. It does not decide anything, and it does not change any system.

## What the tool does not decide

- **Who should have access.** It treats today's access as the baseline. If someone holds a permission they should never have had, the tool will faithfully preserve it. Access reviews are a separate activity (see the first principle in [method.md](method.md)).
- **Whether a segregation-of-duties conflict is acceptable.** It reports conflicts against the rules you supply and never removes access to fix one. Resolution, or an exception with a compensating control, is for the risk owner.
- **Whether a gain of access is acceptable.** It refuses gain-causing merges by default and lists every gain if you allow them. Approving, narrowing or rejecting each is a human call.
- **What a role means.** Generated role names are placeholders based on the most distinctive permission. Business owners should name and own roles.
- **Whether a group is really unused.** "No members" is the only evidence of disuse it has. A group may still be referenced by an integration, a report filter or a procedure.
- **Anything about timing, communication or approvals.** Those are in the method document, not the code.

## What the data model leaves out

The tool sees four flat tables. It does not model:

- **Nested groups, inheritance or role hierarchies.** If a group grants access by containing another group, export the effective permissions instead.
- **Direct grants to users**, administrator flags, ownership-based or attribute-based access, and conditional or time-limited access. Effective access outside the supplied tables is invisible, so "no change" in the report means no change in the supplied data.
- **Data scope.** Many business systems restrict permissions by company, branch, customer or record. Two groups with the same permission names but different scopes would look identical here. Treat identical or near-identical results with suspicion until scope is checked.
- **Permission semantics.** Names are opaque strings. The tool cannot know that two permissions are equivalent, or that one implies another.
- **Usage or activity.** It does not read logs, so it cannot tell which permissions are used.
- **Account status.** Leavers, disabled accounts and service accounts are only as good as the user list you provide.
- **Three-way or quantity-based conflicts.** SoD rules are pairs of permissions. Conflicts involving three permissions, thresholds, or the same transaction are not detected.

## Heuristics and their limits

- **Clustering is greedy.** Complete-linkage clustering with a threshold is deterministic and explainable but not optimal. A human may well find a better grouping.
- **Jaccard treats all permissions as equal.** A group that differs by one low-risk view permission and one that differs by a payment approval score the same. The severity rating partly compensates, using a list of sensitive action names (approve, release, delete, void, admin, adjust, and a few others). That list is a heuristic tied to a `module.action` naming convention. Override it with `--sensitive-actions` and check it against your own naming.
- **Department alignment depends on HR data.** "Dominant department" is the department supplying at least 60% of a group's members. Wrong or stale departments produce wrong alignments.
- **Defaults are not calibrated.** The 0.8 similarity threshold and the zero gain limit are conservative starting points, not findings. The worked example shows how sensitive the result is to them.
- **A union role never removes access.** That is deliberate, and it means a restructure alone will not reduce privilege. It also means a role can be broader than any individual needs.

## Evidence that the tool is correct

The test suite covers the similarity maths, SoD detection, the rule that gains are prevented or listed, determinism, input validation and the report output. Passing tests show the code does what it says. They do not show that the heuristics suit your organisation. The tool has been run on synthetic data only.

## Human review is required

Before any change to a live system, at minimum:

1. A named owner reviews every proposed role and the groups it replaces.
2. Every `review_required = YES` row in `impact.csv` has a recorded disposition.
3. Someone confirms the export was complete and current at the time of analysis.
4. The cut-over has a tested rollback plan.
5. The outputs are retained with the change record.

## Security caveats

- **The inputs and outputs are sensitive.** They list who holds which access, which is useful to an attacker as well as an auditor. Store them under your access-control and retention policies, restrict who can read them, and delete working copies when finished.
- **Never commit real exports to a public repository.** `.gitignore` excludes the default working folders, but it is not a safeguard against mistakes.
- **No network access.** The tool uses only the standard library and does not make network calls. It reads the CSV files you point it at and writes the output folder.
- **The HTML report is static.** It contains no scripts, and cell contents are escaped. Even so, open reports from untrusted inputs with the same care as any file from an unknown source.
- **Hashes show integrity, not authenticity.** The SHA-256 values in the report prove which bytes were analysed. They do not prove the export was genuine or complete.
- **Advisory output.** Nothing here is a control. A person applying the proposal is responsible for the outcome.
