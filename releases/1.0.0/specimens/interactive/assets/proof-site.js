const faceFamily = document.querySelector("#proof-family");
const italicToggle = document.querySelector("#proof-italic");
const faceStatus = document.querySelector("#face-status");
const proofSample = document.querySelector("#sample-text");
const faceCache = new Map();
let editedSample = false;
let selectedFace;

proofSample.addEventListener("input", () => { editedSample = true; });
if (Array.from(faceFamily.options).some(option => option.value === params.get("family"))) {
  faceFamily.value = params.get("family");
}
italicToggle.checked = params.get("italic") === "1";
if (params.get("view") !== "glyphs") proofMode.value = "text";

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
    activateProof(data);
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
proofMode.addEventListener("change", () => {
  const url = new URL(location.href);
  url.searchParams.set("view", proofMode.value);
  history.replaceState(null, "", url);
});
selectFace();
