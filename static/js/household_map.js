(function () {
  const MAPBOX_TOKEN = 'pk.eyJ1IjoicmFwaGJlbGwiLCJhIjoiY21jNHN6ODhtMDRteDJpcHdocXJpaTFpaiJ9.tkV7UFKy4yBlAtkZNYOS4A';
  mapboxgl.accessToken = MAPBOX_TOKEN;

  // ── Barangay Sto. Niño boundary (lng, lat)
  const stoNinoBoundary = {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [[
        [123.90212, 10.29731],
        [123.90201, 10.29786],
        [123.90058, 10.29764],
        [123.89806, 10.29617],
        [123.89771, 10.29501],
        [123.89805, 10.29378],
        [123.89904, 10.29427],
        [123.89994, 10.29420],
        [123.89934, 10.29213],
        [123.89938, 10.29193],
        [123.90009, 10.29210],
        [123.90065, 10.28980],
        [123.90212, 10.29069],
        [123.90181, 10.29169],
        [123.90195, 10.29180],
        [123.90196, 10.29194],
        [123.90334, 10.29488],
        [123.90359, 10.29580],
        [123.90382, 10.29723],
        [123.90379, 10.29753],
        [123.90213, 10.29724],
        [123.90212, 10.29731]
      ]]
    },
    properties: { name: "Barangay Sto. Niño" }
  };

  const PUROK_COLORS = {
    "KANIPAAN":    "#7B1E22",
    "PAMPANGO":    "#D4AF37",
    "LUTAW-LUTAW": "#4f46e5",
    "MAUCO":       "#16a34a",
  };

  function buildPurokQuads(boundary) {
    const [minX, minY, maxX, maxY] = turf.bbox(boundary);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    const rect = (x1, y1, x2, y2) =>
      turf.polygon([[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]);
    const quads = [
      { code: 'S01', name: 'KANIPAAN',     poly: rect(minX, midY, midX, maxY) },
      { code: 'S02', name: 'PAMPANGO',     poly: rect(midX,  midY, maxX, maxY) },
      { code: 'S03', name: 'LUTAW-LUTAW',  poly: rect(minX,  minY, midX,  midY) },
      { code: 'S04', name: 'MAUCO',        poly: rect(midX,  minY, maxX,  midY) },
    ];
    const features = [];
    for (const q of quads) {
      const clipped = turf.intersect(q.poly, boundary);
      if (clipped) {
        features.push({
          type: 'Feature',
          properties: { code: q.code, name: q.name },
          geometry: clipped.geometry
        });
      }
    }
    return { type: 'FeatureCollection', features };
  }

  const purokFc = buildPurokQuads(stoNinoBoundary);

  const map = new mapboxgl.Map({
    container: 'purokMap',
    style: 'mapbox://styles/mapbox/streets-v11',
    center: [123.9028, 10.2951],
    zoom: 16,
    attributionControl: true
  });

  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }));

  let markers = [];                     // array of mapboxgl.Marker
  const markerById = new Map();         // household_id -> Marker
  let focusMarker = null;

  function buildPinsUrl() {
    const base = window.__PINS_URL__ || "/api/household/pins/";
    const url = new URL(base, window.location.origin);
    ["search", "house_type", "house_ownership"].forEach(k => {
      const v = new URL(window.location.href).searchParams.get(k);
      if (v !== null && v !== "") url.searchParams.set(k, v);
    });
    return url.toString();
  }

  function popupHtml(p) {
    const esc = s => (s ?? "").toString().replace(/[&<>"']/g, m =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])
    );

    // Prefer canonical field names, with graceful fallbacks
    const hhNum   = p.household_num || p.hh_num || p.number || "";
    const head    = p.household_head || p.head_name || p.title || "";
    const address = p.address_line || p.household_address ||
      [p.street, p.purok, p.barangay, p.city].filter(Boolean).join(", ");
    const htype   = p.house_type_name || p.house_type || "";
    const hown    = p.household_ownership_name || p.ownership_type_name ||
                    p.house_ownership_name || p.house_ownership || "";

    // Household No., Head, Address, Type, Ownership
    return `
      <div style="min-width:240px; line-height:1.25">
        ${hhNum ? `<div><strong>${esc(hhNum)}</strong></div>` : ``}
        ${head  ? `<div>${esc(head)}</div>` : ``}
        ${address ? `<div class="text-muted">${esc(address)}</div>` : ``}
        ${(htype || hown) ? `<div style="margin-top:6px">
          ${htype ? `Type: ${esc(htype)}<br/>` : ``}
          ${hown  ? `Ownership: ${esc(hown)}` : ``}
        </div>` : ``}
      </div>
    `;
  }

  function makeMarker(p, lng, lat) {
    const purokName = (p.purok || "").toUpperCase();
    const color = (PUROK_COLORS && PUROK_COLORS[purokName]) || "#6d2932"; // default brand color
    const marker = new mapboxgl.Marker({ color })
      .setLngLat([lng, lat])
      .setPopup(new mapboxgl.Popup({ offset: 12 }).setHTML(popupHtml(p)));
    marker.addTo(map);
    return marker;
  }

  function clearMarkers() {
    markers.forEach(m => m.remove());
    markers = [];
    markerById.clear();
  }

  function fitTo(points) {
    if (!points.length) return;
    const bounds = new mapboxgl.LngLatBounds();
    points.forEach(p => bounds.extend([p.__lng, p.__lat]));
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 40, maxZoom: 17, duration: 600 });
  }

  // ────────────────────────────────────────────────────────────
  // COINCIDENT MARKER HANDLING (Spiderfy-light)
  // ────────────────────────────────────────────────────────────

  // Group pins by identical coordinates (rounded)
  function groupPinsByCoord(pins, precision = 6) {
    const groups = new Map(); // key -> array
    for (const p of pins) {
      if (p.lat == null || p.lng == null) continue;
      const key = `${Number(p.lat).toFixed(precision)}|${Number(p.lng).toFixed(precision)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(p);
    }
    return groups;
  }

  // Spread a group around the original point using Turf.destination
  function spreadGroup(baseLng, baseLat, n) {
    const R = 3; // meters
    const coords = [];
    const start = Math.random() * 360;
    for (let i = 0; i < n; i++) {
      const bearing = start + (360 / n) * i;
      const dest = turf.destination([baseLng, baseLat], R, bearing, { units: "meters" });
      coords.push(dest.geometry.coordinates); // [lng, lat]
    }
    return coords;
  }

  // Returns array of points with injected __lng/__lat (possibly offset)
  function spiderfyIfNeeded(pins) {
    const out = [];
    const groups = groupPinsByCoord(pins, 6);

    for (const [key, arr] of groups.entries()) {
      if (arr.length === 1) {
        const p = arr[0];
        p.__lng = p.lng;
        p.__lat = p.lat;
        out.push(p);
        continue;
      }
      // Multiple at same spot: spread around
      const [latStr, lngStr] = key.split("|"); // key is lat|lng
      const baseLat = parseFloat(latStr);
      const baseLng = parseFloat(lngStr.split("|")[0] || lngStr); // safety
      const positions = spreadGroup(baseLng, baseLat, arr.length);

      arr.forEach((p, idx) => {
        const [lng, lat] = positions[idx];
        p.__lng = lng;
        p.__lat = lat;
        p.__spider_origin = [baseLng, baseLat];
        p.__spider_index = idx + 1;
        p.__spider_count = arr.length;
        out.push(p);
      });
    }
    return out;
  }

  async function loadPins() {
    clearMarkers();
    try {
      const res = await fetch(buildPinsUrl(), { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const pins = await res.json();

      console.log("[household_map] pins (raw):", pins.length, pins);

      const spreadPins = spiderfyIfNeeded(
        pins.filter(p => p.lat != null && p.lng != null)
      );

      console.log("[household_map] pins (spread):", spreadPins.length, spreadPins);

      spreadPins.forEach(p => {
        const m = makeMarker(p, p.__lng, p.__lat);
        markers.push(m);
        // Map by household_id → marker (string key for consistency)
        const hid = p.household_id != null ? p.household_id : p.id;
        if (hid != null) markerById.set(String(hid), m);
      });

      fitTo(spreadPins);
    } catch (e) {
      console.error("[household_map] loadPins failed:", e);
    }
  }

  function wireLocateClicks() {
    // Works for:
    //  - .js-locate-hh  with data-hid (recommended)
    //  - .js-locate     with data-hid (if you reuse class)
    document.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".js-locate-hh, .js-locate");
      if (!btn) return;

      const hid = btn.getAttribute("data-hid");
      const marker = hid ? markerById.get(String(hid)) : null;

      if (marker) {
        const { lng, lat } = marker.getLngLat();
        map.flyTo({ center: [lng, lat], zoom: 18, speed: 1.2, curve: 1.4 });
        marker.togglePopup();
        return;
      }

      // Fallback if marker not found (e.g., limited pins to current page)
      const lat = parseFloat(btn.getAttribute("data-lat"));
      const lng = parseFloat(btn.getAttribute("data-lng"));
      if (isFinite(lat) && isFinite(lng)) {
        if (focusMarker) focusMarker.remove();
        focusMarker = new mapboxgl.Marker({ color: "#6d2932" })
          .setLngLat([lng, lat])
          .addTo(map);
        map.flyTo({ center: [lng, lat], zoom: 18, speed: 1.2, curve: 1.4 });
      }
    });
  }

  map.on("load", () => {
    // Fit to barangay boundary and draw layers
    const bbox = turf.bbox(stoNinoBoundary);
    map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 30, duration: 0 });

    map.addSource('sto-nino-BG', { type: 'geojson', data: stoNinoBoundary });
    map.addSource('puroks',      { type: 'geojson', data: purokFc });

    map.addLayer({ id: 'sto-nino-fill', type: 'fill', source: 'sto-nino-BG',
      paint: { 'fill-color': '#000', 'fill-opacity': 0.06 }});
    map.addLayer({ id: 'sto-nino-outline', type: 'line', source: 'sto-nino-BG',
      paint: { 'line-color': '#111', 'line-width': 2 }});
    map.addLayer({ id: 'purok-fill', type: 'fill', source: 'puroks',
      paint: {
        'fill-color': [
          'match', ['get', 'name'],
          'KANIPAAN',    '#7B1E22',
          'PAMPANGO',    '#D4AF37',
          'LUTAW-LUTAW', '#4f46e5',
          'MAUCO',       '#16a34a',
          /* other */    '#999'
        ],
        'fill-opacity': 0.28
      }});
    map.addLayer({ id: 'purok-outline', type: 'line', source: 'puroks',
      paint: { 'line-color': '#333', 'line-width': 1.2 }});
    map.addLayer({ id: 'purok-labels', type: 'symbol', source: 'puroks',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 12,
        'text-offset': [0, 0.6],
        'text-anchor': 'top',
        'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold']
      },
      paint: { 'text-halo-color': '#fff', 'text-halo-width': 1 }
    });

    loadPins();
    wireLocateClicks();
  });
})();
