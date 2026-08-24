// Typst template for an imported ChatGPT transcript.
//
// Consumed by scripts/render_pdf.py, which emits a document that imports this
// file and then calls #turn(...) once per message. Turns are split by the
// renderer rather than detected by a show-rule, so the styling never depends on
// parsing heading text back out of content.
//
// Speaker labels are passed in, not hardcoded: the same transcript is rendered
// once as "User" for machine context and once under a real name for reading.

#let theme = (
  user: (bg: rgb("#eef2ff"), accent: rgb("#4338ca")),
  assistant: (bg: rgb("#f7f7f8"), accent: rgb("#0f766e")),
  other: (bg: rgb("#fdf6e3"), accent: rgb("#92400e")),
)

// Returns a flat array of two cells, or an empty array when there is no value.
// A function that *emits* two cells instead of returning them would be folded
// into a single cell by Typst, which silently packs four fields onto one row.
#let meta-cells(k, v) = if v == none or v == "" { () } else {
  (
    text(fill: luma(110), size: 8.5pt)[#k],
    text(size: 8.5pt)[#v],
  )
}

#let conversation(
  title: "ChatGPT conversation",
  date_held: "",
  model: "",
  user_label: "User",
  assistant_label: "ChatGPT",
  turns: 0,
  user_messages: 0,
  assistant_messages: 0,
  source_url: "",
  captured_at: "",
  redacted: false,
  paper: "a4",
  body,
) = {
  set document(title: title)
  set page(
    paper: paper,
    margin: (x: 2.2cm, y: 2.2cm),
    footer: context [
      #set text(size: 8pt, fill: luma(130))
      #title
      #h(1fr)
      #counter(page).display("1 / 1", both: true)
    ],
  )
  set text(font: ("Inter", "Noto Sans", "DejaVu Sans"), size: 10pt, lang: "en")
  set par(justify: false, leading: 0.62em, spacing: 1.1em)

  show link: it => text(fill: theme.assistant.accent, underline(it))
  show raw.where(block: false): it => box(
    fill: luma(242), inset: (x: 3pt, y: 1pt), outset: (y: 2pt), radius: 2pt, it,
  )
  show raw.where(block: true): it => block(
    fill: luma(246), inset: 8pt, radius: 4pt, width: 100%,
    text(size: 8.5pt, it),
  )
  // Headings inside a message are already demoted by the renderer; keep them
  // visibly subordinate to the speaker banner.
  show heading: it => block(above: 1.1em, below: 0.6em,
    text(size: 10pt, weight: "bold", it.body))

  // ---- cover block -------------------------------------------------------
  block(width: 100%)[
    #text(size: 18pt, weight: "bold")[#title]
    #v(0.3em)
    #text(size: 9pt, fill: luma(110))[Imported ChatGPT conversation]
    #if redacted [ #h(0.5em) #box(fill: rgb("#fee2e2"), inset: (x: 4pt, y: 1pt),
      radius: 2pt, text(size: 8pt, fill: rgb("#991b1b"), weight: "bold")[REDACTED]) ]
  ]
  v(0.6em)
  line(length: 100%, stroke: 0.5pt + luma(200))
  v(0.6em)

  grid(
    columns: (auto, 1fr),
    column-gutter: 1.2em,
    row-gutter: 0.4em,
    ..meta-cells("Date held", date_held),
    ..meta-cells("Model", model),
    ..meta-cells("Turns", str(turns)),
    ..meta-cells(user_label, str(user_messages) + " messages"),
    ..meta-cells(assistant_label, str(assistant_messages) + " messages"),
    ..meta-cells("Source", source_url),
    ..meta-cells("Captured", captured_at),
  )
  v(1.2em)

  body
}

// One message. `kind` selects the palette; `label` is the displayed speaker.
#let turn(kind: "user", label: "", stamp: "", body) = {
  let t = if kind == "user" { theme.user }
          else if kind == "assistant" { theme.assistant }
          else { theme.other }

  block(
    breakable: true,
    width: 100%,
    inset: (left: 10pt, right: 10pt, top: 8pt, bottom: 8pt),
    fill: t.bg,
    radius: 4pt,
    stroke: (left: 2.5pt + t.accent),
    spacing: 0.9em,
  )[
    #block(below: 0.55em)[
      #text(size: 9pt, weight: "bold", fill: t.accent)[#label]
      #if stamp != "" [
        #h(0.5em) #text(size: 7.5pt, fill: luma(140))[#stamp]
      ]
    ]
    #body
  ]
}

// A generated document, image or attachment noted inline.
#let artifact(kind: "", name: "") = block(
  width: 100%, inset: 6pt, radius: 3pt,
  fill: rgb("#fffbeb"), stroke: 0.5pt + rgb("#f59e0b"), spacing: 0.7em,
)[
  #text(size: 8.5pt, weight: "bold", fill: rgb("#92400e"))[Artifact — #kind]
  #if name != "" [ #text(size: 8.5pt)[: #name] ]
]

// Cited sources, listed once at the end.
#let sources(items) = if items.len() > 0 {
  pagebreak(weak: true)
  block(above: 1.4em, below: 0.7em)[
    #text(size: 13pt, weight: "bold")[Sources]
  ]
  for it in items [
    #block(spacing: 0.5em)[
      #text(size: 8.5pt, fill: luma(110))[#str(it.n).] #h(0.3em)
      #text(size: 9pt, weight: "medium")[#it.title] \
      #h(1.1em) #text(size: 8pt)[#link(it.url)[#it.url]]
    ]
  ]
}
