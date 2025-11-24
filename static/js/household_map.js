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
  let allPins = [];                     // store all pins for filtering
  let activeFilter = null;              // track active filter

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
    console.log('[popupHtml] Pin data:', p);
    const esc = s => (s ?? "").toString().replace(/[&<>"']/g, m =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])
    );

    const hhNum   = p.household_num || p.hh_num || p.number || "";
    const head    = p.household_head || p.head_name || p.title || "";
    const address = p.address_line || p.household_address ||
      [p.street, p.purok, p.barangay, p.city].filter(Boolean).join(", ");
    const htype   = p.house_type_name || p.house_type || "";
    const hown    = p.household_ownership_name || p.ownership_type_name ||
                    p.house_ownership_name || p.house_ownership || "";
    const hasVisitData = p.visited !== undefined;
    const visited = p.visited ? "Visited" : "Not Visited";
    const visitColor = p.visited ? "#16a34a" : "#dc2626";
    const famVisited = p.families_visited || 0;
    const famNotVisited = p.families_not_visited || 0;

    return `
      <div style="min-width:240px; line-height:1.25">
        ${hhNum ? `<div><strong>${esc(hhNum)}</strong></div>` : ``}
        ${head  ? `<div>${esc(head)}</div>` : ``}
        ${address ? `<div class="text-muted">${esc(address)}</div>` : ``}
        ${(htype || hown) ? `<div style="margin-top:6px">
          ${htype ? `Type: ${esc(htype)}<br/>` : ``}
          ${hown  ? `Ownership: ${esc(hown)}<br/>` : ``}
        </div>` : ``}
        ${hasVisitData ? `<div style="margin-top:6px; color:${visitColor}; font-weight:bold">${visited}</div>` : ``}
        ${hasVisitData ? `<div style="margin-top:4px; font-size:0.9em">
          ${famVisited > 0 ? `<span style="color:#16a34a">${famVisited} ${famVisited === 1 ? 'family' : 'families'} visited</span>` : `<span style="color:#999">0 families visited</span>`}
          <br/>
          ${famNotVisited > 0 ? `<span style="color:#dc2626">${famNotVisited} ${famNotVisited === 1 ? 'family' : 'families'} not visited</span>` : `<span style="color:#999">0 families not visited</span>`}
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

  function showMarkers(pinsToShow) {
    clearMarkers();
    const spreadPins = spiderfyIfNeeded(
      pinsToShow.filter(p => p.lat != null && p.lng != null)
    );
    spreadPins.forEach(p => {
      const m = makeMarker(p, p.__lng, p.__lat);
      markers.push(m);
      const hid = p.household_id != null ? p.household_id : p.id;
      if (hid != null) markerById.set(String(hid), m);
    });
    if (spreadPins.length > 0) fitTo(spreadPins);
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

  window.loadPins = async function() {
    clearMarkers();
    try {
      const res = await fetch(buildPinsUrl(), { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const pins = await res.json();

      console.log("[household_map] pins (raw):", pins.length, pins);
      allPins = pins;
      showMarkers(pins);
    } catch (e) {
      console.error("[household_map] loadPins failed:", e);
    }
  };

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

  let currentPins = allPins;
  
  function handleCardClick(type) {
    const cards = document.querySelectorAll('.visit-card');
    cards.forEach(c => {
      const small = c.querySelector('small');
      if (small && small.textContent.includes('Showing')) {
        small.innerHTML = small.innerHTML.replace('check-circle', 'eye').replace('Showing', 'View on map');
      }
    });

    let filtered;
    if (type === 'households_visited') {
      filtered = currentPins.filter(p => p.visited === true);
    } else if (type === 'households_not_visited') {
      filtered = currentPins.filter(p => p.visited === false);
    } else if (type === 'families_visited') {
      filtered = currentPins.filter(p => (p.families_visited || 0) > 0);
    } else if (type === 'families_not_visited') {
      filtered = currentPins.filter(p => (p.families_not_visited || 0) > 0);
    } else {
      filtered = currentPins;
    }

    activeFilter = type;
    showMarkers(filtered);

    const card = document.querySelector(`.visit-card[data-filter="${type}"]`);
    if (card) {
      const small = card.querySelector('small');
      if (small) {
        small.innerHTML = small.innerHTML.replace('eye', 'check-circle').replace('View on map', 'Showing');
      }
    }
  }

  window.showOnMap = handleCardClick;
  
  window.filterByPurok = function(purok) {
    myAreaActive = false;
    const btn = document.getElementById('showMyAreaBtn');
    if (btn) {
      const icon = btn.querySelector('.bi');
      if (icon) icon.className = 'bi bi-geo-alt-fill';
      btn.style.background = '';
    }
    
    if (purok) {
      const filtered = allPins.filter(p => (p.purok || '').toUpperCase() === purok.toUpperCase());
      currentPins = filtered;
      showMarkers(filtered);
      updateCardCounts(filtered);
    } else {
      currentPins = allPins;
      showMarkers(allPins);
      updateCardCounts(allPins);
    }
  };
  
  let myAreaActive = false;
  
  window.showMyArea = function(purokNames) {
    if (myAreaActive) {
      myAreaActive = false;
      currentPins = allPins;
      showMarkers(allPins);
      const btn = document.getElementById('showMyAreaBtn');
      if (btn) {
        const icon = btn.querySelector('.bi');
        if (icon) icon.className = 'bi bi-geo-alt-fill';
        btn.style.background = '';
      }
      updateCardCounts(allPins);
      return;
    }
    
    myAreaActive = true;
    const filtered = allPins.filter(p => {
      const purokUpper = (p.purok || '').toUpperCase();
      return purokNames.some(name => purokUpper === name.toUpperCase());
    });
    currentPins = filtered;
    showMarkers(filtered);
    
    const btn = document.getElementById('showMyAreaBtn');
    if (btn) {
      const icon = btn.querySelector('.bi');
      if (icon) icon.className = 'bi bi-check-circle';
      btn.style.background = '#16a34a';
    }
    updateCardCounts(filtered);
  };
  
  function updateCardCounts(pins) {
    const hh_v = pins.filter(p => p.visited === true).length;
    const hh_nv = pins.filter(p => p.visited === false).length;
    const fam_v = pins.reduce((sum, p) => sum + (p.families_visited || 0), 0);
    const fam_nv = pins.reduce((sum, p) => sum + (p.families_not_visited || 0), 0);
    
    document.querySelectorAll('.visit-card').forEach(card => {
      const filter = card.getAttribute('data-filter');
      const count = card.querySelector('.count');
      if (filter === 'households_visited') count.textContent = hh_v;
      else if (filter === 'households_not_visited') count.textContent = hh_nv;
      else if (filter === 'families_visited') count.textContent = fam_v;
      else if (filter === 'families_not_visited') count.textContent = fam_nv;
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

    window.loadPins();
    wireLocateClicks();
    
    if (window.__pendingFilter) {
      console.log('[household_map] Applying pending filter:', window.__pendingFilter);
      setTimeout(() => handleCardClick(window.__pendingFilter), 500);
      window.__pendingFilter = null;
    }
  });
})();
