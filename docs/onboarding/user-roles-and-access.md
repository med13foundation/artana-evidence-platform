# User Roles and Access

This guide explains access in plain language.

MED13 uses two layers of roles:

1. **System roles** control access to platform-wide features such as user management, audit logs, PHI access, and system settings.
2. **Research space roles** control what someone can do inside a specific research space.

## How to read this

- A person always has one **system role**.
- A person may also have a different **research space role** in each space they belong to.
- Most day-to-day collaboration happens through the **research space role**.
- **System admins** are special: they can access admin pages and are treated as admins in every research space.
- Under the current policy, **PHI access is only granted to system admins**.

## System Roles

| System role | What they can usually see | What they can usually do | Good fit for |
| --- | --- | --- | --- |
| **Admin** | Everything, including admin-only pages like Dictionary, Audit Logs, PHI Access, and System Settings | Manage users, change roles, suspend or remove accounts, review audit data, manage global settings, and support all research spaces | Platform operators and trusted administrators |
| **Curator** | Standard signed-in areas and the spaces they belong to | Work with data and curation workflows, but **cannot** open system admin pages or manage the platform | Senior data stewards who review and refine content |
| **Researcher** | Standard signed-in areas and the spaces they belong to | Create and work with research content in their spaces, but **cannot** manage the platform or access PHI-only areas | Scientists and analysts doing active research work |
| **Viewer** | Read-only areas they have access to | View data in their spaces, but **cannot** run write actions, curation actions, or platform administration | Stakeholders who need visibility without editing power |

### Plain-English summary

- **Admin** = full platform control
- **Curator** = review and improve data, but not platform administration
- **Researcher** = create and work with research content
- **Viewer** = read-only access

## Research Space Roles

Research space roles are more important for day-to-day work inside a space.

| Research space role | What they can see | What they can do | Good fit for |
| --- | --- | --- | --- |
| **Owner** | Everything in the space | Full control of the space, including settings and member management | The person accountable for the space |
| **Admin** | Everything in the space | Manage members, manage space settings, and oversee the space | Space leads and coordinators |
| **Curator** | All space content needed for review | Review and approve content, manage curation decisions, and handle higher-trust content workflows | Curators and reviewers |
| **Researcher** | All regular working areas in the space | Create and update entities, relations, concepts, hypotheses, and run ingestion or pipeline workflows | Researchers doing active work in the space |
| **Viewer** | Read-only space pages and data | View content, follow progress, and inspect results without changing them | Observers, collaborators, and leadership readers |

### Plain-English summary

- **Owner/Admin** = run the space
- **Curator** = review and approve work
- **Researcher** = create and update work
- **Viewer** = read-only

## What changes by role inside a research space

| Activity | Owner/Admin | Curator | Researcher | Viewer |
| --- | --- | --- | --- | --- |
| Open the space and read data | Yes | Yes | Yes | Yes |
| Manage members | Yes | No | No | No |
| Edit space settings | Yes | No | No | No |
| Create or update research content | Yes | Yes | Yes | No |
| Review or approve curation decisions | Yes | Yes | No | No |
| Run ingestion and pipeline workflows | Yes | Yes | Yes | No |

## Common examples

| Example person | System role | Space role | What this usually means |
| --- | --- | --- | --- |
| Platform administrator | Admin | Admin in all spaces by default | Can manage the platform and help in any space |
| Lead curator in one project | Curator | Curator | Can review and approve work in that project, but cannot open global admin pages |
| Research scientist | Researcher | Researcher | Can create and update work in their project, but cannot approve final curation decisions |
| Executive observer | Viewer | Viewer | Can read progress and results without changing anything |

## One important rule

Being powerful at the **system** level does not automatically replace the need for a clear **space** role for everyday collaboration, except for system admins.

In practice:

- If someone is not a member of a research space, they usually cannot access that space.
- If they are a **system admin**, they can still access the space for support and administration.
