# Usability direction

Research and implementation notes, October 23, 2026. Guidelines inform design decisions; they do not establish that Railet is usable without testing with actual dealership staff.

## Design rules

- Home offers real tasks using familiar action labels. No disabled future modules, marketing promises, or decorative metrics.
- Navigation shows where the user is. Labels use dealership language rather than module architecture.
- Show essential choices first. Put secondary filters behind an explicit control, preserving visibility of applied filters.
- Group forms by the user's purpose: vehicle details, title information, costs/notes. Keep title verification explicit, rather than guessing reassuring defaults.
- Preserve submissions and show actionable errors. Don't hide errors or required information to make a page appear simpler.
- Use established controls, visible keyboard focus, labeled fields, readable contrast and responsive layout. Icons supplement text, never replace it.
- Don't add a multi-step wizard merely to claim simplicity. Use steps only if testing shows they help, and preserve work between them.

## Validation to perform with dealership staff

Ask a new user to add a synthetic vehicle, find it again, and correct its title information without coaching. Observe hesitation, wrong turns, errors and whether they know the task succeeded. Record actual results before setting performance targets or claiming the design is intuitive. Repeat for deals and payments only when implemented.

## Sources

Nielsen Norman Group, 10 Usability Heuristics: familiar language, recognition, error prevention, minimalism, and feedback. https://www.nngroup.com/articles/ten-usability-heuristics/

Nielsen Norman Group, Progressive Disclosure: offer important choices first and reveal specialized options on request. https://www.nngroup.com/articles/progressive-disclosure/

GOV.UK Design System, Navigate a service: simplify journeys first and distinguish repeated navigation from ordered transaction tasks. https://design-system.service.gov.uk/patterns/navigate-a-service/

These sources support the principles, not a claim that one particular layout is universally best.
