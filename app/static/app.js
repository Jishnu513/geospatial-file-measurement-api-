/**
 * Geospatial File Measurement API — Client-Side Application Logic
 */

let map = null;
let currentGeoJsonLayer = null;
let activeTileLayer = null;
let isSatellite = false;
let currentFileId = null;
let currentGeojsonData = null;
let currentMeasurementsData = null;

// Tile layers
const darkTiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
  maxZoom: 19
});

const satelliteTiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
  maxZoom: 18
});

document.addEventListener('DOMContentLoaded', () => {
  initMap();
  initDropzone();
  fetchRecentFiles();
  // Auto-load calibration square benchmark on first load
  loadSampleDataset('sample_known_square.kml');
});

function initMap() {
  map = L.map('map', {
    center: [0, 0],
    zoom: 3,
    zoomControl: true
  });

  activeTileLayer = darkTiles;
  activeTileLayer.addTo(map);
}

function toggleMapLayer() {
  if (!map) return;
  map.removeLayer(activeTileLayer);
  if (isSatellite) {
    activeTileLayer = darkTiles;
    isSatellite = false;
    document.getElementById('layer-label').textContent = 'Satellite';
  } else {
    activeTileLayer = satelliteTiles;
    isSatellite = true;
    document.getElementById('layer-label').textContent = 'Dark Map';
  }
  activeTileLayer.addTo(map);
}

function initDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-over');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length > 0) {
      uploadFile(fileInput.files[0]);
    }
  });
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  showToast(`Uploading ${file.name}...`, 'info');

  try {
    const res = await fetch('/api/files/', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await res.json();
    showToast(`Successfully processed ${file.name}`, 'success');
    currentFileId = data.id;
    await inspectFile(currentFileId);
    fetchRecentFiles();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

async function loadSampleDataset(sampleName) {
  showToast(`Loading benchmark dataset: ${sampleName}...`, 'info');

  try {
    const res = await fetch(`/api/files/samples/${encodeURIComponent(sampleName)}/process`, {
      method: 'POST'
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to load sample');
    }

    const data = await res.json();
    showToast(`Loaded ${sampleName} (${data.feature_count} features)`, 'success');
    currentFileId = data.id;
    await inspectFile(currentFileId);
    fetchRecentFiles();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

async function inspectFile(fileId) {
  currentFileId = fileId;

  try {
    // 1. Fetch info
    const infoRes = await fetch(`/api/files/${fileId}/`);
    const info = await infoRes.json();

    // 2. Fetch measurements
    const measRes = await fetch(`/api/files/${fileId}/measurements/`);
    const meas = await measRes.json();
    currentMeasurementsData = meas;

    // 3. Fetch GeoJSON
    const geoRes = await fetch(`/api/files/${fileId}/features/`);
    const geojson = await geoRes.json();
    currentGeojsonData = geojson;

    // Update UI
    renderMetadataCard(info, meas);
    renderSummaryCard(meas.summary);
    renderFeaturesList(meas.measurements);
    renderMeasurementsTable(meas.measurements);
    renderMapGeoJson(geojson, meas);
    renderCodeBlocks(fileId, meas, geojson);

  } catch (err) {
    showToast(`Failed to inspect file: ${err.message}`, 'error');
  }
}

function renderMetadataCard(info, meas) {
  document.getElementById('file-metadata-card').style.display = 'block';
  document.getElementById('meta-filename').textContent = info.filename;
  document.getElementById('meta-status').textContent = info.status;
  document.getElementById('meta-crs').textContent = info.crs || 'EPSG:4326';
  document.getElementById('meta-count').textContent = info.feature_count;
  document.getElementById('meta-time').textContent = `${info.processing_time_ms || 0} ms`;

  // Find projected CRS from first supported feature
  let projCrs = 'Auto UTM Zone';
  if (meas.measurements && meas.measurements.length > 0) {
    for (const m of meas.measurements) {
      if (m.properties && m.properties._projected_crs) {
        projCrs = m.properties._projected_crs;
        break;
      }
    }
  }
  document.getElementById('meta-proj').textContent = projCrs;
}

function renderSummaryCard(summary) {
  if (!summary) return;
  document.getElementById('summary-card').style.display = 'block';

  document.getElementById('sum-area-m2').textContent = `${Number(summary.total_area_sq_m || 0).toLocaleString()} m²`;
  document.getElementById('sum-area-ha').textContent = `${(summary.total_area_hectares || 0).toFixed(4)} ha | ${(summary.total_area_acres || 0).toFixed(4)} acres`;

  document.getElementById('sum-length-m').textContent = `${Number(summary.total_length_m || 0).toLocaleString()} m`;
  document.getElementById('sum-length-km').textContent = `${(summary.total_length_km || 0).toFixed(4)} km`;

  document.getElementById('sum-supported').textContent = summary.supported_features_count || 0;
  document.getElementById('sum-unsupported').textContent = summary.unsupported_features_count || 0;
}

function renderFeaturesList(features) {
  const container = document.getElementById('feature-items-container');
  const countBadge = document.getElementById('features-badge-count');
  document.getElementById('features-list-card').style.display = 'block';
  
  container.innerHTML = '';
  countBadge.textContent = features.length;

  features.forEach((f, idx) => {
    const item = document.createElement('div');
    item.className = 'feature-item';
    item.id = `feat-item-${idx}`;

    let measurementText = 'No measurement';
    if (f.supported && f.measurements) {
      if (f.measurements.area) {
        measurementText = `Area: ${Number(f.measurements.area.sq_meters).toLocaleString()} m² (${f.measurements.area.hectares} ha)`;
      } else if (f.measurements.length) {
        measurementText = `Length: ${Number(f.measurements.length.meters).toLocaleString()} m`;
      } else if (f.measurements.total_area) {
        measurementText = `Collection Area: ${f.measurements.total_area.sq_meters} m²`;
      }
    }

    const name = f.properties?.name || `Feature #${f.feature_id}`;

    item.innerHTML = `
      <div class="feat-info">
        <span class="feat-title">${name}</span>
        <span class="feat-sub">${measurementText}</span>
      </div>
      <span class="feat-badge">${f.geometry_type}</span>
    `;

    item.addEventListener('click', () => {
      document.querySelectorAll('.feature-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      zoomToFeature(idx);
    });

    container.appendChild(item);
  });
}

function renderMeasurementsTable(features) {
  const tbody = document.getElementById('measurements-table-body');
  tbody.innerHTML = '';

  features.forEach((f, idx) => {
    const tr = document.createElement('tr');

    let primaryMetric = '<span style="color: var(--text-muted);">&mdash;</span>';
    let geodesicMetric = '<span style="color: var(--text-muted);">&mdash;</span>';
    let projCrs = f.properties?._projected_crs || 'Auto UTM';

    if (f.supported && f.measurements) {
      if (f.measurements.area) {
        const a = f.measurements.area;
        primaryMetric = `<strong>${Number(a.sq_meters).toLocaleString()} m²</strong><br><small style="color: var(--accent-cyan);">${a.hectares} ha | ${a.acres} ac</small>`;
        if (f.measurements.geodesic_area_sq_meters) {
          const geoA = f.measurements.geodesic_area_sq_meters;
          const diffPct = Math.abs((a.sq_meters - geoA) / geoA * 100).toFixed(3);
          geodesicMetric = `<strong>${Number(geoA).toLocaleString()} m²</strong><br><small style="color: var(--accent-emerald);">Δ ${diffPct}% ellipsoid</small>`;
        }
      } else if (f.measurements.length) {
        const l = f.measurements.length;
        primaryMetric = `<strong>${Number(l.meters).toLocaleString()} m</strong><br><small style="color: var(--accent-cyan);">${l.kilometers} km | ${l.feet} ft</small>`;
        if (f.measurements.geodesic_length_meters) {
          const geoL = f.measurements.geodesic_length_meters;
          const diffPct = Math.abs((l.meters - geoL) / geoL * 100).toFixed(3);
          geodesicMetric = `<strong>${Number(geoL).toLocaleString()} m</strong><br><small style="color: var(--accent-emerald);">Δ ${diffPct}% ellipsoid</small>`;
        }
      }
    }

    const statusBadge = f.supported
      ? '<span class="status-badge status-completed">Measured</span>'
      : '<span class="status-badge status-processing">Ignored (0D)</span>';

    tr.innerHTML = `
      <td><strong>#${f.feature_id}</strong> ${f.properties?.name ? `<br><small style="color: var(--text-secondary);">${f.properties.name}</small>` : ''}</td>
      <td><span class="feat-badge">${f.geometry_type}</span></td>
      <td>${statusBadge}</td>
      <td>${primaryMetric}</td>
      <td>${geodesicMetric}</td>
      <td><small style="color: var(--accent-blue);">${projCrs}</small></td>
      <td>
        <button class="copy-btn" onclick="zoomToFeature(${idx})">
          <i class="fa-solid fa-crosshairs"></i> Zoom
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderMapGeoJson(geojson, meas) {
  if (!map) return;

  if (currentGeoJsonLayer) {
    map.removeLayer(currentGeoJsonLayer);
  }

  currentGeoJsonLayer = L.geoJSON(geojson, {
    style: (feature) => {
      return {
        color: '#00f2fe',
        weight: 2.5,
        opacity: 0.9,
        fillColor: '#00f2fe',
        fillOpacity: 0.25,
        dashArray: feature.geometry.type === 'LineString' ? '6, 6' : null
      };
    },
    pointToLayer: (feature, latlng) => {
      return L.circleMarker(latlng, {
        radius: 8,
        fillColor: '#f43f5e',
        color: '#ffffff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.8
      });
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      const m = p._measurements;
      const featId = feature.id || p._feature_id;

      let measHtml = '<div style="margin-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 0.4rem;">';
      if (m && m.area) {
        measHtml += `
          <div><strong>Area (Projected):</strong> ${Number(m.area.sq_meters).toLocaleString()} m² (${m.area.hectares} ha)</div>
          <div><strong>Perimeter:</strong> ${Number(m.perimeter?.meters || 0).toLocaleString()} m</div>
          ${m.geodesic_area_sq_meters ? `<div><strong>Geodesic WGS84:</strong> ${Number(m.geodesic_area_sq_meters).toLocaleString()} m²</div>` : ''}
        `;
      } else if (m && m.length) {
        measHtml += `
          <div><strong>Length:</strong> ${Number(m.length.meters).toLocaleString()} m (${m.length.kilometers} km)</div>
          ${m.geodesic_length_meters ? `<div><strong>Geodesic WGS84:</strong> ${Number(m.geodesic_length_meters).toLocaleString()} m</div>` : ''}
        `;
      } else {
        measHtml += `<div style="color: #94a3b8;">Point Coordinate: [${feature.geometry?.coordinates?.join(', ') || ''}]</div>`;
      }
      measHtml += '</div>';

      layer.bindPopup(`
        <div style="font-family: inherit; font-size: 0.85rem; color: #fff; background: #172133; padding: 0.5rem; border-radius: 8px;">
          <h4 style="margin: 0; color: #00f2fe; font-size: 0.95rem;">${p.name || `Feature #${featId}`}</h4>
          <div style="font-size: 0.75rem; color: #94a3b8;">Type: ${p._geometry_type || feature.geometry.type}</div>
          ${measHtml}
        </div>
      `);
    }
  });

  currentGeoJsonLayer.addTo(map);
  fitMapToBounds();
}

function fitMapToBounds() {
  if (currentGeoJsonLayer && currentGeoJsonLayer.getLayers().length > 0) {
    map.fitBounds(currentGeoJsonLayer.getBounds(), { padding: [40, 40], maxZoom: 16 });
  }
}

function zoomToFeature(index) {
  if (!currentGeoJsonLayer) return;
  const layers = currentGeoJsonLayer.getLayers();
  if (layers[index]) {
    const layer = layers[index];
    if (layer.getBounds) {
      map.fitBounds(layer.getBounds(), { padding: [80, 80], maxZoom: 17 });
    } else if (layer.getLatLng) {
      map.setView(layer.getLatLng(), 16);
    }
    layer.openPopup();
  }
}

function renderCodeBlocks(fileId, meas, geojson) {
  document.getElementById('json-meas-code').textContent = JSON.stringify(meas, null, 2);
  document.getElementById('geojson-code').textContent = JSON.stringify(geojson, null, 2);

  const curl = `# Retrieve File Info
curl "http://localhost:8000/api/files/${fileId}/"

# Retrieve Measurements
curl "http://localhost:8000/api/files/${fileId}/measurements/"

# Retrieve with Unit Filter (?unit=ha)
curl "http://localhost:8000/api/files/${fileId}/measurements/?unit=ha"

# Retrieve GeoJSON FeatureCollection
curl "http://localhost:8000/api/files/${fileId}/features/"

# Delete File
curl -X DELETE "http://localhost:8000/api/files/${fileId}/"`;

  document.getElementById('curl-code').textContent = curl;
}

async function fetchRecentFiles() {
  const container = document.getElementById('recent-files-container');
  try {
    const res = await fetch('/api/files/?limit=10');
    const data = await res.json();

    if (!data.files || data.files.length === 0) {
      container.innerHTML = `<div style="font-size: 0.75rem; color: var(--text-muted); text-align: center; padding: 1rem;">No files uploaded yet.</div>`;
      return;
    }

    container.innerHTML = '';
    data.files.forEach(f => {
      const item = document.createElement('div');
      item.className = 'feature-item';
      item.innerHTML = `
        <div class="feat-info">
          <span class="feat-title">${f.filename}</span>
          <span class="feat-sub">${f.feature_count} features &bull; ${f.file_type}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <button class="copy-btn" onclick="event.stopPropagation(); inspectFile('${f.id}')">Inspect</button>
          <button class="copy-btn" style="color: var(--accent-rose);" onclick="event.stopPropagation(); deleteFile('${f.id}')"><i class="fa-solid fa-trash"></i></button>
        </div>
      `;
      item.addEventListener('click', () => inspectFile(f.id));
      container.appendChild(item);
    });
  } catch (err) {
    container.innerHTML = `<div style="font-size: 0.75rem; color: var(--accent-rose); text-align: center; padding: 1rem;">Failed to load history</div>`;
  }
}

async function deleteFile(fileId) {
  if (!confirm('Are you sure you want to delete this file record?')) return;
  try {
    const res = await fetch(`/api/files/${fileId}/`, { method: 'DELETE' });
    if (res.ok) {
      showToast('File deleted successfully', 'success');
      fetchRecentFiles();
      if (currentFileId === fileId) {
        // Reset view
        loadSampleDataset('sample_known_square.kml');
      }
    }
  } catch (err) {
    showToast(`Failed to delete: ${err.message}`, 'error');
  }
}

function switchTab(tabId, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

  document.getElementById(tabId).classList.add('active');
  btn.classList.add('active');
}

function copyCode(elementId) {
  const text = document.getElementById(elementId).textContent;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Copied to clipboard!', 'success');
  });
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : ''}`;
  
  const icon = type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-circle-xmark' : 'fa-circle-info';
  toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${msg}</span>`;
  
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}
