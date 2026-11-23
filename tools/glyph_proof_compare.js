function createAxisComparison(config, svg, refresh) {
  const {family, axes, codepoints, guides, centerStyle, upm, labelWidth, fontSize, margin,
         baselineOffset, headerY, detailHeader, pageWidth, pageHeight} = config;
  const toolbar = document.querySelector("#axis-controls");
  const status = document.querySelector("#axis-status");
  const sampleText = document.querySelector("#sample-text");
  const sampleSize = document.querySelector("#sample-size");
  const allPresets = document.querySelector("#all-presets");
  const textSamples = document.querySelector("#text-samples");
  const listeners = new AbortController();
  const {signal} = listeners;
  const fixedFields = document.createElement("div");
  fixedFields.className = "control";
  const axis = document.createElement("select");
  axis.id = "compare-axis";
  for (const [tag, spec] of Object.entries(axes)) axis.add(new Option(spec.label, tag));
  const defaultAxis = axes.wght ? "wght" : axis.value;
  axis.value = defaultAxis;

  function labeled(label, field) {
    const group = document.createElement("div");
    group.className = "control";
    const caption = document.createElement("label");
    caption.htmlFor = field.id;
    caption.textContent = label;
    group.append(caption, field);
    return group;
  }

  const defaults = Object.fromEntries(Object.entries(axes).map(([tag, spec]) => [tag, spec.value]));
  const values = {...defaults};
  const reset = document.createElement("button");
  reset.type = "button";
  reset.textContent = "Reset axes";
  toolbar.append(labeled("Compare", axis), fixedFields, reset);
  toolbar.hidden = false;

  function showFields() {
    fixedFields.replaceChildren();
    for (const [tag, spec] of Object.entries(axes)) {
      if (tag === axis.value) continue;
      const input = document.createElement("input");
      input.type = "number";
      input.id = "axis-" + tag;
      input.min = spec.min;
      input.max = spec.max;
      input.step = "any";
      input.value = values[tag];
      input.title = spec.label + " range: " + spec.min.toPrecision(6) + "–" + spec.max.toPrecision(6);
      const presets = document.createElement("select");
      presets.id = input.id + "-preset";
      for (const [value, label] of spec.stops) presets.add(new Option(label, value));
      presets.add(new Option("Custom…", "custom"));
      presets.value = spec.stops.some(([value]) => value === values[tag]) ? values[tag] : "custom";
      const custom = labeled("Custom " + spec.label.toLowerCase(), input);
      custom.hidden = presets.value !== "custom";
      fixedFields.append(labeled(spec.label, presets), custom);
      presets.addEventListener("change", () => {
        custom.hidden = presets.value !== "custom";
        if (custom.hidden) {
          values[tag] = Number(presets.value);
          input.value = values[tag];
          apply();
        } else {
          input.focus();
          input.select();
        }
      });
      input.addEventListener("change", () => {
        if (input.validity.valid && Number.isFinite(input.valueAsNumber)) values[tag] = input.valueAsNumber;
        input.value = values[tag];
        apply();
      });
    }
  }

  const changed = () => axis.value !== defaultAxis || Object.keys(values).some(tag => values[tag] !== defaults[tag]);
  let loaded = false;
  let failed = false;
  let loading;
  let face;
  function loadFont() {
    if (loading) return;
    status.textContent = "Loading comparison…";
    face = new FontFace("TransitProof", "url(data:font/woff2;base64," + config.font + ")");
    loading = face.load().then(() => {
      if (signal.aborted) return;
      document.fonts.add(face);
      loaded = true;
      status.textContent = "";
      refresh();
    }).catch(() => {
      if (signal.aborted) return;
      toolbar.hidden = true;
      failed = true;
      status.textContent = "The proof font could not load. Reload the page to try again.";
      if (svg) {
        document.querySelector("#mode-control").hidden = true;
        document.querySelector("#proof-mode").value = "glyphs";
        status.textContent = "Live comparisons could not load. The vector proof is available below.";
      }
      refresh();
    });
  }

  function apply() {
    reset.disabled = !changed();
    if (changed()) loadFont();
    refresh();
  }

  axis.addEventListener("change", () => {
    showFields();
    apply();
  });
  reset.addEventListener("click", () => {
    Object.assign(values, defaults);
    axis.value = defaultAxis;
    showFields();
    apply();
    axis.focus();
  });
  showFields();
  reset.disabled = true;

  function setLocation(node, location) {
    node.style.fontVariationSettings = Object.entries(location).map(([tag, value]) => '"' + tag + '" ' + value).join(", ");
  }

  function setTextMode(typing) {
    fixedFields.hidden = typing && allPresets.checked;
    if (!typing) return;
    if (!loaded) {
      loadFont();
      return;
    }
    const current = axes[axis.value];
    let groups = [{location: values, labels: []}];
    if (allPresets.checked) {
      for (const [tag, spec] of Object.entries(axes)) {
        if (tag === axis.value) continue;
        groups = groups.flatMap(group => spec.stops.map(([value, label]) => ({
          location: {...group.location, [tag]: value}, labels: [...group.labels, label],
        })));
      }
    }
    const sections = groups.map(({location, labels}) => {
      const section = document.createElement("section");
      section.className = "sample-group";
      const heading = document.createElement("h2");
      heading.textContent = labels.join(" · ") || "Compare by " + current.label.toLowerCase();
      section.append(heading);
      for (const [value, label] of current.stops) {
        const row = document.createElement("div");
        row.className = "text-sample";
        const caption = document.createElement("span");
        caption.className = "text-sample-label";
        caption.textContent = label;
        const text = document.createElement("p");
        text.className = "text-sample-value";
        text.dir = "auto";
        text.textContent = sampleText.value;
        setLocation(text, {...location, [axis.value]: value});
        row.append(caption, text);
        section.append(row);
      }
      return section;
    });
    textSamples.replaceChildren(...sections);
  }

  allPresets.addEventListener("change", refresh, {signal});
  sampleText.addEventListener("input", () => {
    for (const sample of textSamples.querySelectorAll(".text-sample-value")) sample.textContent = sampleText.value;
  }, {signal});
  sampleSize.addEventListener("input", () => {
    if (sampleSize.validity.valid && Number.isFinite(sampleSize.valueAsNumber)) {
      textSamples.style.setProperty("--sample-size", sampleSize.valueAsNumber + "px");
    }
  }, {signal});

  function element(parent, name, attributes, content) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    if (content !== undefined) node.textContent = content;
    parent.append(node);
    return node;
  }

  function line(parent, x1, y1, x2, y2, style) {
    element(parent, "line", {x1, y1, x2, y2, style, "stroke-width": 0.55});
  }

  function glyphSample(parent, row, value) {
    const text = element(parent, "text", {x: 0, y: 0, class: "axis-sample", fill: "#151b1b",
                                       "font-family": "TransitProof", "font-size": fontSize},
                         String.fromCodePoint(codepoints[row.name]));
    text.style.fontOpticalSizing = "none";
    setLocation(text, {...values, [axis.value]: value});
    return text;
  }

  function fitSamples(texts, cell) {
    const samples = texts.map(text => {
      const box = text.getBBox();
      const advance = text.getComputedTextLength();
      const origin = advance ? advance / 2 : box.x + box.width / 2;
      return {box, origin, extent: Math.max(advance / 2, origin - box.x, box.x + box.width - origin)};
    });
    const extent = Math.max(1, ...samples.map(sample => sample.extent));
    return {
      scale: Math.min(1, (cell / 2 - 4) / extent),
      origins: samples.map(sample => sample.origin),
      top: Math.min(0, ...samples.map(({box}) => box.y)),
      bottom: Math.max(0, ...samples.map(({box}) => box.y + box.height)),
    };
  }

  function drawGuides(parent, left, right, baseline, scale) {
    for (const [, units, style] of guides) {
      const y = baseline - units * fontSize * scale / upm;
      line(parent, left, y, right, y, style);
    }
  }

  function placeGlyph(text, origin, scale, center, baseline) {
    text.setAttribute("transform", "translate(" + center + " " + baseline + ") scale(" + scale +
                      ") translate(" + (-origin) + " 0)");
  }

  function render(page, entries, selected) {
    const width = selected ? selected.box[2] : pageWidth;
    const height = selected ? selected.box[3] + detailHeader : pageHeight;
    const activeAxis = axes[axis.value];
    const stops = activeAxis.stops;
    svg.setAttribute("viewBox", [0, 0, width, height].join(" "));
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.setAttribute("aria-label", (selected?.label || page) + " by " + activeAxis.label.toLowerCase());
    svg.replaceChildren();
    element(svg, "rect", {width, height, fill: "#fff"});
    if (!selected) {
      element(svg, "text", {x: margin, y: 43, "font-size": 27, "font-weight": 700},
              family);
      element(svg, "text", {x: margin, y: 76, "font-size": 20, "font-weight": 700}, page);
      let legendX = 473;
      const legend = [...guides, ["Advance / ink center", null, centerStyle]];
      for (const [label, units, style] of legend) {
        const text = units === null ? label : label + " " + Number(units.toPrecision(6));
        line(svg, legendX, 73, legendX + 17, 73, style);
        element(svg, "text", {x: legendX + 22, y: 77, "font-size": 10, fill: "#454b47"}, text);
        legendX += 28 + text.length * 5.5;
      }
    }

    const items = selected ? [selected] : entries;
    const groupHeaders = new Set();
    for (const row of items) {
      const [x, y, block, rowHeight] = selected ? [0, detailHeader, ...row.box.slice(2)] : row.box;
      const baseline = y + baselineOffset;
      const cell = (block - labelWidth) / stops.length;
      const center = i => x + labelWidth + (i + 0.5) * cell;
      if (!groupHeaders.has(x)) {
        const labelY = selected ? detailHeader - 8 : headerY;
        stops.forEach(([, label], i) => {
          const size = Math.min(11, (cell - 8) / label.length / 0.57);
          element(svg, "text", {x: center(i), y: labelY, "text-anchor": "middle",
                                "font-size": size, fill: "#435451"}, label);
        });
        groupHeaders.add(x);
      }
      element(svg, "rect", {x, y, width: block, height: rowHeight - 1, fill: row.shade});
      const labelSize = Math.min(12, (labelWidth - 12) / row.label.length / 0.57);
      element(svg, "text", {x: x + 8, y: y + 29, "font-size": labelSize, fill: "#454b47"}, row.label);
      const rules = element(svg, "g", {"aria-hidden": true});
      const texts = stops.map(([value]) => glyphSample(svg, row, value));
      const {scale, origins} = fitSamples(texts, cell);
      drawGuides(rules, x + labelWidth, x + block, baseline, scale);
      texts.forEach((text, i) => {
        line(rules, center(i), y + 3, center(i), y + rowHeight - 3, centerStyle);
        placeGlyph(text, origins[i], scale, center(i), baseline);
      });
    }
  }

  function renderRows(container, groups) {
    if (!loaded) {
      if (!failed) loadFont();
      return;
    }
    const stops = axes[axis.value].stops;
    const cell = 72;
    const height = 51;
    const pending = [];
    const legend = document.createElement("ul");
    legend.className = "proof-guides";
    legend.setAttribute("aria-label", "Glyph guides");
    for (const [label, , style] of [...guides, ["Advance / ink center", null, centerStyle]]) {
      const item = document.createElement("li");
      const swatch = element(item, "svg", {width: 20, height: 8, "aria-hidden": true});
      line(swatch, 1, 4, 19, 4, style);
      item.append(label);
      legend.append(item);
    }
    const sections = groups.map(([title, rows]) => {
      const section = document.createElement("section");
      const heading = document.createElement("h2");
      heading.textContent = title;
      const table = document.createElement("table");
      table.setAttribute("aria-label", title);
      const header = table.createTHead().insertRow();
      for (const label of ["Glyph", ...stops.map(([, label]) => label)]) {
        const column = document.createElement("th");
        column.scope = "col";
        column.textContent = label;
        header.append(column);
      }
      const body = table.createTBody();
      for (const row of rows) {
        const tableRow = body.insertRow();
        const label = document.createElement("th");
        label.scope = "row";
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.glyph = row.name;
        button.textContent = row.label;
        label.append(button);
        tableRow.append(label);
        const samples = stops.map(([value]) => {
          const picture = element(tableRow.insertCell(), "svg", {
            viewBox: "0 0 " + cell + " " + height, width: cell, height, "aria-hidden": true,
          });
          return {picture, rules: element(picture, "g", {}), text: glyphSample(picture, row, value)};
        });
        pending.push(samples);
      }
      section.append(heading, table);
      return section;
    });
    container.replaceChildren(legend, ...sections);
    const layouts = pending.map(samples => fitSamples(samples.map(({text}) => text), cell));
    pending.forEach((samples, index) => {
      const {scale, origins, top, bottom} = layouts[index];
      const rowTop = Math.min(0, Math.floor(baselineOffset + top * scale) - 2);
      const rowBottom = Math.max(height, Math.ceil(baselineOffset + bottom * scale) + 2);
      samples.forEach(({picture, rules, text}, i) => {
        picture.setAttribute("viewBox", "0 " + rowTop + " " + cell + " " + (rowBottom - rowTop));
        picture.setAttribute("height", rowBottom - rowTop);
        drawGuides(rules, 0, cell, baselineOffset, scale);
        line(rules, cell / 2, rowTop + 3, cell / 2, rowBottom - 3, centerStyle);
        placeGlyph(text, origins[i], scale, cell / 2, baselineOffset);
      });
    });
  }

  function dispose() {
    listeners.abort();
    if (face) document.fonts.delete(face);
    toolbar.replaceChildren();
    status.textContent = "";
    textSamples.replaceChildren();
  }

  return {active: () => loaded && changed(), render, renderRows, setTextMode, dispose};
}
