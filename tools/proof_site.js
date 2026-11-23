const faceFamily = document.querySelector("#proof-family");
const italicToggle = document.querySelector("#proof-italic");
const faceStatus = document.querySelector("#face-status");
const proofSample = document.querySelector("#sample-text");
const proofMode = document.querySelector("#proof-mode");
const groupPicker = document.querySelector("#proof-group");
const glyphPicker = document.querySelector("#proof-glyph");
const glyphFilters = document.querySelector("#glyph-filters");
const gallery = document.querySelector("#glyph-proof");
const typeProof = document.querySelector("#type-proof");
const faceCache = new Map();
const params = new URLSearchParams(location.search);
let groups = {};
let comparison;
let editedSample = false;
let selectedFace;

proofSample.addEventListener("input", () => { editedSample = true; });
if (Array.from(faceFamily.options).some(option => option.value === params.get("family"))) {
  faceFamily.value = params.get("family");
}
italicToggle.checked = params.get("italic") === "1";
if (params.get("view") === "glyphs") proofMode.value = "glyphs";
document.querySelector("#all-presets").checked = params.get("presets") === "all";

function visibleGroups() {
  return groupPicker.value ? [[groupPicker.value, groups[groupPicker.value]]] : Object.entries(groups);
}

function renderProof() {
  if (!comparison) return;
  const typing = proofMode.value === "text";
  typeProof.hidden = !typing;
  glyphFilters.hidden = gallery.hidden = typing;
  comparison.setTextMode(typing);
  if (!typing) {
    const glyph = glyphPicker.value;
    const sections = glyph
      ? visibleGroups().map(([title, rows]) => [title, rows.filter(row => row.name === glyph)])
          .filter(([, rows]) => rows.length)
      : visibleGroups();
    comparison.renderRows(gallery, sections);
  }
}

function updateGlyphs() {
  const selected = glyphPicker.value;
  const byName = new Map(visibleGroups().flatMap(([, rows]) => rows.map(row => [row.name, row.label])));
  glyphPicker.replaceChildren(new Option("All glyphs", ""),
    ...Array.from(byName, ([name, label]) => new Option(label, name)));
  if (byName.has(selected)) glyphPicker.value = selected;
  renderProof();
}

async function selectFace() {
  const family = faceFamily.value;
  const italic = italicToggle.checked;
  const face = {family, italic};
  selectedFace = face;
  const file = family + "/" + (italic ? "italic" : "upright") + "/proof.json";
  faceStatus.textContent = "Loading face…";
  try {
    if (!faceCache.has(file)) {
      const response = await fetch(file);
      if (!response.ok) throw new Error("Proof data could not be loaded");
      faceCache.set(file, await response.json());
    }
    if (selectedFace !== face) return;
    const data = faceCache.get(file);
    if (!editedSample) proofSample.value = data.example;
    document.querySelector("#print-face").textContent = data.comparison.family + (italic ? " Italic" : "");
    comparison?.dispose();
    gallery.replaceChildren();
    groups = data.groups;
    const selectedGroup = groupPicker.value;
    groupPicker.replaceChildren(new Option("All groups", ""),
      ...Object.keys(groups).map(title => new Option(title, title)));
    if (Object.hasOwn(groups, selectedGroup)) groupPicker.value = selectedGroup;
    comparison = createAxisComparison(data.comparison, null, renderProof);
    updateGlyphs();
    const url = new URL(location.href);
    url.searchParams.set("family", family);
    if (italic) url.searchParams.set("italic", "1");
    else url.searchParams.delete("italic");
    history.replaceState(null, "", url);
    faceStatus.textContent = "";
  } catch {
    if (selectedFace === face) {
      faceStatus.textContent = "This face could not load. Choose another face or reload the page to retry.";
    }
  }
}

faceFamily.addEventListener("change", selectFace);
italicToggle.addEventListener("change", selectFace);
groupPicker.addEventListener("change", updateGlyphs);
glyphPicker.addEventListener("change", renderProof);
gallery.addEventListener("click", event => {
  const button = event.target.closest("button[data-glyph]");
  if (!button) return;
  glyphPicker.value = glyphPicker.value === button.dataset.glyph ? "" : button.dataset.glyph;
  renderProof();
  glyphPicker.focus();
});
proofMode.addEventListener("change", () => {
  const url = new URL(location.href);
  url.searchParams.set("view", proofMode.value);
  history.replaceState(null, "", url);
  renderProof();
});
selectFace();
