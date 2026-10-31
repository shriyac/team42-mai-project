# Layer ownership and integration boundaries

| Area | Owner | Responsibilities |
| --- | --- | --- |
| frontend/src/components, main.jsx, styles.css, public | UI team | Rendering, accessibility, interaction, design tokens, responsive behavior |
| frontend/src/services | Integration boundary | Gateway method signatures and HTTP mapping; coordinated changes with contract owner |
| frontend/src/data | UI team | Fictional fixtures, imported only by mockGateway |
| frontend/src/lib | Shared frontend | Pure formatters and policy-date helpers; no HTTP, storage or Python dependencies |
| contracts/openapi.json | Joint API owner | Versioned schemas, routes, status codes and compatibility review |
| src/laga | Python backend team | Authentication, authorization, persistence, files, ingestion, retrieval, tools and validation |
| docs/INTERFACE_CONTRACT.md | Joint API owner | Behavioral invariants not fully expressible in JSON schemas |

Components call a gateway passed by the app; they do not import fixtures, call fetch, parse PDFs or access storage directly. HTTP and mock adapters expose the same methods. The Python team must not need to edit UI components to replace the mock service. Domain changes start with the contract and examples; keep existing required fields compatible or increment the API version.

Tenant means customer in the UI; the wire role is `tenant`. Policy admin is a permission (`policies:write`) attached to a landlord account, rather than a third identity type. Backend role and object-level checks are required on every endpoint.

CSS is hierarchical: root tokens and primitives, shell, feature components, responsive overrides. All typography inherits the self-hosted Manrope font. Icons use lucide-react; property illustrations and the Laga mark are local SVG. No external asset services are required.

Avoid editing other owners' layers during parallel development. Propose contract changes in review, update both adapters, and run `npm test` and `npm run build`. Keep backend secrets in server environment variables; VITE variables are public bundle configuration.

The included Python scaffold is deliberately untouched by the interface implementation. The existing MVP plan is design context, not a claim that RAG has been implemented.
