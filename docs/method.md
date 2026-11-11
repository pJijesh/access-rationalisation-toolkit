# A method for rationalising legacy access groups

This is the method the tool supports. It is written for an IT or security lead who has inherited a business application with years of accumulated security groups and needs to reduce them without breaking operations or quietly widening anyone's access. It is system-neutral: the steps apply to any platform where users hold groups and groups hold permissions.

The tool covers steps 2 to 4 (analyse, design, map). The rest is people, change control and evidence, which no script can do for you.

## Principles

1. **Preserve access first, reduce it second.** A rationalisation is a restructure, not an access review. Mixing the two makes it impossible to tell whether a user lost access because of the restructure or because of a review decision. Run the access review separately, ideally on the new, smaller model.
2. **No silent privilege gain.** Merging two similar groups usually gives somebody a permission they did not have. That can be acceptable, but only as an explicit, recorded decision. The tool refuses such merges by default and lists every gain when you allow them.
3. **Evidence over opinion.** Every proposed change should trace to a measurement: identical permission sets, no members, a redundant membership, a segregation-of-duties conflict.
4. **Humans own the roles.** The tool proposes. A business owner decides what a role means and who should hold it.
5. **Make rollback boring.** Keep the old groups intact, disabled rather than deleted, until the new model has survived a full business cycle.

## Step 1: Discover

**Goal:** a complete, trustworthy snapshot of who holds what today.

- Export four things from the application or its directory: users (with department and job title), group memberships, the permissions each group grants, and, if you have them, the segregation-of-duties rules your finance or risk function already uses.
- Record when and how each export was taken and who took it. Hash the files (the tool does this for you) so you can show later which data a decision was based on.
- Check completeness before analysing. Do group names in memberships all appear in the permission export? Are there users in memberships who are missing from the user list (the tool rejects these)? Are leavers still present? Are service accounts included, and if so, are they marked?
- Identify an owner for every group. Groups nobody will claim are the first candidates for retirement, but ask before assuming.
- Agree a change freeze for group definitions during the project, or at least a log of changes, so the snapshot does not drift under you.
- Collect the context the export does not contain: which groups exist for reasons other than permissions (mailing lists, reporting filters, integrations), and which permissions are restricted by data scope such as company or branch.

**Output:** four CSV files, an export log, and a list of group owners.

## Step 2: Analyse

**Goal:** understand the mess in numbers before proposing anything.

Run `access-rat analyse` and read the report in this order:

1. **Inventory.** Group sizes, permissions per group, dominant department. Look for groups with no members (candidates to retire), groups that grant nothing, and very large groups that are really baseline access.
2. **Duplicates and near-duplicates.** Jaccard similarity of permission sets finds groups that were copied and tweaked. Jaccard similarity of member sets finds groups that always travel together. A pair with identical permissions is a safe merge. A pair that is merely similar is a question, not an answer.
3. **Redundant memberships.** A membership is redundant when removing it leaves that user's effective permissions identical. A high count suggests access was added by copying a colleague rather than by role.
4. **Excess groups per user.** Users holding more groups than a chosen limit are usually carrying history.
5. **Permissions granted through many groups.** These point to a missing baseline role or to an unclear source of truth.
6. **Segregation-of-duties conflicts.** For each rule, who holds both sides, and through which groups. Also whether a single group contains both sides by itself, which is a design flaw rather than a user problem.

Treat the SoD findings as a separate work stream. Restructuring does not resolve them and the tool deliberately does not try to.

**Output:** the baseline report, kept as evidence of the starting position.

## Step 3: Design roles

**Goal:** a smaller set of roles that business owners recognise.

The tool proposes a model with these rules, in order:

1. Retire groups with no members or no permissions (after confirming with the owner that they serve no other purpose).
2. Cluster groups by permission-set similarity using complete linkage: every pair in a cluster must reach the threshold, which stops chains of loosely related groups.
3. Merge only within a department pattern. Two groups merge when their dominant department matches, or when their permission sets are identical.
4. Never create a role that holds both sides of a segregation-of-duties rule unless one of its source groups already did.
5. Apply the **gain limit**: refuse a merge that would give new access to more than a chosen share of the role's members. The default is zero. Raising it trades consolidation for review effort.

A merged role grants the union of its source groups' permissions, so the model never removes access.

What the tool cannot do, and you should:

- Run a design workshop with each department's business owner. Show them the proposed roles and the groups each replaces. Ask whether the role name and contents match how they think about the job.
- Rename roles. The generated labels (department plus the role's most distinctive permission) are placeholders.
- Decide whether a widely held permission belongs in a baseline role.
- Decide what to do with conflicts and with gains. See Approvals below.

**Output:** an agreed role catalogue with an owner for each role.

## Step 4: Map

**Goal:** a precise, reviewable translation from old to new.

The tool writes two files:

- `mapping.csv`: every old group, the action proposed (retain, merge, retire), the new role, how many permissions the role adds relative to the old group, and how many members would gain access through it.
- `impact.csv`: one row per user, with old groups, new roles, permissions gained and lost, severity, any new SoD conflict, and a `review_required` flag.

Work through `impact.csv` by filtering on `review_required = YES`, sorted by severity. For each user decide one of:

- **Accept** the gain, recording who approved it and why.
- **Narrow** it, by keeping the user on a narrower role or by splitting the role.
- **Keep the original group** for that user for now, and track it as a known exception.

Update the mapping and re-run until the list is either empty or fully dispositioned. Because the output is deterministic, you can show a reviewer exactly what changed between runs.

**Output:** a signed-off mapping and a dispositioned impact list.

## Step 5: Pilot

**Goal:** prove the model on a small, representative population before touching everyone.

- Pick one department with a manageable headcount and a sympathetic manager. Avoid starting with finance or any department in the middle of a close.
- Run in **shadow mode** first where the application allows it: assign the new roles alongside the old groups, change nothing else, and compare what users can actually do. Where it does not, pilot with volunteers and a named support contact.
- Define success criteria in advance: no access-related incidents, no unexplained helpdesk tickets, and a manager confirmation for each pilot user.
- Test the negative cases too: a user who should not be able to do something still cannot.
- Keep the pilot long enough to cover the department's real cycle, such as a month-end close for finance or a peak week for operations.

**Output:** a pilot report with issues found, fixes made, and a go or no-go recommendation.

## Step 6: Cut over

**Goal:** move everyone with a controlled, reversible change.

1. **Prepare.** Take a fresh export and re-run the analysis. If the data has drifted, review the difference before proceeding. Archive the final inputs, parameters and outputs.
2. **Create** the new roles with their permissions. Verify each role's permission list against `roles.csv`.
3. **Assign** users to the new roles in waves, by department, ahead of removing anything. During this period users hold both old groups and new roles.
4. **Verify** per wave: compare effective permissions before and after for a sample, then for all users if the application can report them.
5. **Remove** old group memberships only after verification. Disable the old groups rather than deleting them.
6. **Hypercare.** Staff the helpdesk with someone who has the mapping to hand and can resolve an access query in minutes. Review tickets daily at first.
7. **Close.** After an agreed stabilisation period, delete the disabled groups under change control and update documentation, joiner-mover-leaver procedures and onboarding templates so that new starters are given roles, not legacy groups.

## Step 7: Rollback

Decide the rollback plan before cut-over, not during an incident.

- **What is preserved:** old groups, with memberships exported and stored, remain intact and disabled until the stabilisation period ends.
- **Triggers:** for example, a business-critical process blocked and not fixable by a role adjustment within an agreed time, or a confirmed unintended gain of sensitive access.
- **Procedure:** re-enable the old groups, restore memberships from the export, remove the new role assignments for the affected wave. The mapping file gives the reverse lookup.
- **Decision rights:** name who can call a rollback (usually the change owner with the application owner) and who must be told.
- **Practise it** on the pilot population so the first time is not the real time.

Partial rollback is normal and healthy. It is usually one role and one department, not the whole programme.

## Step 8: Evidence for audit

Auditors and regulators ask three things: what was the state before, what did you decide and who approved it, and what was the state after. Keep:

| Evidence | Why |
| --- | --- |
| Input CSVs and their SHA-256 hashes (in `summary.json`) | Shows which data every decision was based on |
| Parameters and tool version (in the report) | Lets someone reproduce the analysis exactly |
| Baseline and final reports, `mapping.csv`, `impact.csv`, `roles.csv` | The proposal and the per-user effect |
| Dispositions for every `review_required` row, with approver and date | Shows gains were decided, not missed |
| SoD exceptions with compensating control, owner and expiry date | Shows conflicts are managed |
| Pilot report and cut-over checklist, with sign-offs | Shows the change was tested and controlled |
| Post-cut-over export and comparison | Shows the outcome |
| Rollback plan and any rollback executed | Shows resilience |
| Change records and communications sent | Shows stakeholders were informed |

Store these with the change record under your normal retention rules. Treat them as sensitive: they list who holds which access.

## Stakeholders and communication plan

| Stakeholder | Interest | Role in the project | Communication |
| --- | --- | --- | --- |
| Executive sponsor | Risk reduced, no business disruption | Approves scope, timing and risk appetite for gains | Short brief at start, milestone updates, cut-over go or no-go |
| Application owner | Operational stability, supportability | Approves the role catalogue and cut-over plan; can call rollback | Weekly working session |
| Department heads (business owners) | People can do their jobs; accountability for their roles | Own and name roles; approve gains and exceptions for their teams | Design workshop; pilot sign-off; pre-cut-over notice |
| Line managers | Their team is not blocked | Confirm users during pilot and after cut-over | Advance notice with dates, a one-page "what changes for your team" |
| End users | Continuity | Report problems | Short notice before their wave, who to contact, what to check |
| Service desk | Handling the queries | Resolve access tickets using the mapping | Briefing and a quick-reference of old group to new role |
| Security, risk and compliance | Segregation of duties, audit trail | Own the SoD rules, approve exceptions, review evidence | Baseline findings early; evidence pack at close |
| Internal or external audit | Control effectiveness | Review evidence | Evidence pack on request |
| Vendor or managed service partner | Technical changes in the platform | Make changes if you cannot; advise on limits | Change request with the mapping attached |
| HR | Accurate department and job-title data; joiner-mover-leaver process | Correct source data; adopt role-based onboarding | Data quality issues found; process change notice |

Communicate in the language of the audience. Users need to know what to expect and who to call. Owners need the decisions they must make. Auditors need the evidence trail. Avoid sending the technical report to everyone.

## Approvals

Define in advance who can approve what, and write it into the change record.

| Decision | Approver | Evidence required |
| --- | --- | --- |
| Role catalogue and names | Business owner of each department, with the application owner | Workshop notes, signed catalogue |
| Merging non-identical groups (a gain exists) | Business owner and security | The per-user list from `impact.csv` with a disposition for each row |
| A gain that is HIGH (new SoD conflict or a sensitive action) | Business owner, security and the risk owner | Written justification; consider narrowing instead |
| Retiring groups with no members | Group owner, or the application owner if there is none | Evidence the group is unused for other purposes |
| SoD exception | Risk owner | Compensating control, named owner, expiry date, review schedule |
| Pilot go or no-go | Application owner and pilot department head | Pilot report |
| Cut-over | Change board or equivalent | Plan, rollback plan, communications, evidence so far |
| Rollback | Change owner with the application owner | Trigger met, per the plan |

Keep approvals proportionate. A rationalisation that creates no gains and retires empty groups needs far less ceremony than one that widens access. The gain limit exists so you can choose which of those two projects you are running.
