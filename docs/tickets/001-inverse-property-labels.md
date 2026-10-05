# Ticket: Serialize inverse property labels

## Context

OntoME imports one property for an inverse pair. The inverse property's label
must be written as `inverseLabel` inside the exported property's `label`
element. It must not be created as a second `property` element.

The legacy `graph_to_ontome.ipynb` notebook implemented this behavior for
CRM-style identifiers. It skipped identifiers matching `...L13i_...`, followed
`owl:inverseOf` from the retained property, and copied the inverse property's
`rdfs:label` values into `inverseLabel` by language.

The current importer instead treats both resources as publishable properties
and serializes `owl:inverseOf` as an XML `inverseOf` relation. This disagrees
with the OntoME import workflow described by the import team.

## Expected XML

For this RDF pair:

```text
L13_used_parameters owl:inverseOf L13i_parameters_for
L13_used_parameters rdfs:label "used parameters"@en
L13i_parameters_for rdfs:label "parameters for"@en
```

generate one XML property:

```xml
<property>
  <identifierInNamespace>L13</identifierInNamespace>
  <label lang="en">
    <standardLabel>used parameters</standardLabel>
    <inverseLabel>parameters for</inverseLabel>
  </label>
</property>
```

Do not emit `L13i_parameters_for` as a separate XML property. Do not emit an
XML `inverseOf` relation for this pair.

## Scope

- Detect inverse pairs from explicit `owl:inverseOf` assertions.
- Select one canonical exported property per pair.
- For the CRM convention, prefer the identifier without the inverse `i`
  suffix, such as `L13` over `L13i`.
- Copy the inverse property's `rdfs:label` into `inverseLabel` when both
  labels have the same language.
- Record the source triples and the inverse-label transformation in the trace
  and generation audit.
- Keep the original labels and domain/range of the selected property.

## Open Decision

Define a reviewed rule for inverse pairs that do not follow the CRM `...i_`
identifier convention. The implementation must not silently choose one side
when neither property has an unambiguous canonical form.

## Acceptance Criteria

- A CRMdig pair such as `L13` and `L13i` produces one XML `property`.
- The generated property contains `standardLabel` and `inverseLabel` for each
  supported shared language.
- The generated XML contains no `inverseOf` element for the collapsed pair.
- The inverse resource is not presented as independently publishable in the
  review workflow.
- A pair with no unambiguous canonical property remains a reviewed blocker.
- Generation trace and audit identify the source labels and inverse relation
  used for the transformation.
- Tests cover CRMdig naming, multiple languages, missing matching languages,
  and ambiguous inverse pairs.

## References

- Legacy behavior: `origin/main:graph_to_ontome.ipynb`.
- XML contract: `resources/xsd/ontome-import-2026-09-15.xsd` supports
  `label/standardLabel` and optional `label/inverseLabel`.
- Current serializer: `src/ontome_importer/xml_writer.py` emits `inverseOf`.
