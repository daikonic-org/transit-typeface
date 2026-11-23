function createAxisComparison(config, svg, refresh) {
  const {family, axes, codepoints, guides, centerStyle, upm, labelWidth, fontSize, margin,
         baselineOffset, headerY, detailHeader, pageWidth, pageHeight} = config;
  const toolbar = document.querySelector("#axis-controls");
  const status = document.querySelector("#axis-status");
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
  let loading;
  function apply() {
    reset.disabled = !changed();
    if (changed() && !loading) {
      status.textContent = "Loading comparison…";
      const face = new FontFace("TransitProof", "url(data:font/woff2;base64," + config.font + ")");
      loading = face.load().then(() => {
        document.fonts.add(face);
        loaded = true;
        status.textContent = "";
        refresh();
      }).catch(() => {
        toolbar.hidden = true;
        status.textContent = "Live axis comparisons could not load. The vector proof is available below.";
      });
    }
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
      const samples = stops.map(([value]) => {
        const location = {...values, [axis.value]: value};
        const text = element(svg, "text", {x: 0, y: 0, class: "axis-sample", fill: "#151b1b",
                                           "font-family": "TransitProof", "font-size": fontSize},
                             String.fromCodePoint(codepoints[row.name]));
        text.style.fontOpticalSizing = "none";
        text.style.fontVariationSettings = Object.entries(location).map(([tag, v]) => '"' + tag + '" ' + v).join(", ");
        const advance = text.getComputedTextLength();
        const origin = advance ? advance / 2 : row.inkCenter * fontSize / upm;
        return {text, origin, advance};
      });
      const extent = Math.max(row.extent * fontSize / upm, ...samples.map(sample => sample.advance / 2));
      const scale = Math.min(1, (cell / 2 - 4) / extent);
      for (const [, units, style] of guides) {
        const guideY = baseline - units * fontSize * scale / upm;
        line(rules, x + labelWidth, guideY, x + block, guideY, style);
      }
      samples.forEach(({text, origin}, i) => {
        line(rules, center(i), y + 3, center(i), y + rowHeight - 3, centerStyle);
        text.setAttribute("transform", "translate(" + center(i) + " " + baseline + ") scale(" + scale +
                          ") translate(" + (-origin) + " 0)");
      });
    }
  }

  return {active: () => loaded && changed(), render};
}
