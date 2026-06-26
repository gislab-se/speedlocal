from __future__ import annotations

import json
from typing import Any


def build_landscape_map_html(
    feature_collection: dict[str, Any],
    center: list[float],
    zoom: int,
    mode: str,
    title: str,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.72,
    legend_items: list[dict[str, str]] | None = None,
) -> str:
    payload = json.dumps(feature_collection, ensure_ascii=False)
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    mode_payload = json.dumps(mode)
    title_payload = json.dumps(title, ensure_ascii=False)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    legend_payload = json.dumps(legend_items or [], ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note {{ background: rgba(255,255,255,0.94); padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 240px; }}
    .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); line-height: 1.25; max-width: 260px; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 6px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {payload};
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const mode = {mode_payload};
    const mapTitle = {title_payload};
    const vectorLayerOpacity = {opacity_payload};
    const legendItems = {legend_payload};
    const map = L.map('map', {{ preferCanvas: true }}).setView(defaultCenter, {int(zoom)});

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function styleFeature(feature) {{
      const props = feature.properties || {{}};
      const fill = mode === 'factor' ? props.factor_fill : props.cluster_fill;
      return {{
        color: mode === 'factor' ? '#666666' : '#444444',
        weight: mode === 'factor' ? 0.25 : 0.35,
        opacity: Math.min(0.85, hexFillOpacity + 0.1),
        fillColor: fill || '#999999',
        fillOpacity: hexFillOpacity
      }};
    }}

    const landscape = L.geoJSON(data, {{
      style: styleFeature,
      onEachFeature: function(feature, layer) {{
        const props = feature.properties || {{}};
        layer.bindPopup(props.popup || props.hex_id || mapTitle);
      }}
    }}).addTo(map);

    const overlays = {{}};
    overlays[mapTitle] = landscape;
    L.control.layers({{ 'OSM': osm, 'Satellite': satellite }}, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + mapTitle + '</strong><br>' + (mode === 'factor' ? 'Faktorscore från manifest.' : 'Kluster från manifest.');
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    if (legendItems.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = '<div class="map-legend-title">' + mapTitle + '</div>' +
          legendItems.map(function(item) {{
            const shapeClass = item.shape === 'circle' ? ' circle' : '';
            return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
          }}).join('');
        L.DomEvent.disableClickPropagation(div);
        return div;
      }};
      legend.addTo(map);
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        return;
      }}
      const dataBounds = landscape.getBounds();
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
    }}
    setTimeout(fitInitialBounds, 80);
  </script>
</body>
</html>
"""


def build_layered_hex_map_html(
    layers: list[dict[str, Any]],
    center: list[float],
    zoom: int,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.78,
    map_state_key: str | None = None,
    map_reset_token: int | str = 0,
    note_title: str = "Samlad potential",
    note_body: str = "Aktiva lager styrs i appen och kan även slås av/på i kartkontrollen.",
) -> str:
    layers_payload = json.dumps(layers, ensure_ascii=False)
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    map_state_key_payload = json.dumps(map_state_key or "")
    map_reset_token_payload = json.dumps(str(map_reset_token))
    note_title_payload = json.dumps(str(note_title), ensure_ascii=False)
    note_body_payload = json.dumps(str(note_body), ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note, .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 280px; }}
    .map-legend {{ line-height: 1.25; max-height: 420px; overflow-y: auto; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 7px; }}
    .map-legend-section {{ font-weight: 700; margin: 7px 0 4px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const layerSpecs = {layers_payload};
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const vectorLayerOpacity = {opacity_payload};
    const mapStateKey = {map_state_key_payload};
    const mapResetToken = {map_reset_token_payload};
    const noteTitle = {note_title_payload};
    const noteBody = {note_body_payload};

    function browserStorage() {{
      try {{
        const storage = window.localStorage;
        const testKey = '__regional_energy_potential_map_test__';
        storage.setItem(testKey, '1');
        storage.removeItem(testKey);
        return storage;
      }} catch (err) {{
        return null;
      }}
    }}

    const viewStorage = browserStorage();

    function storageKey(kind) {{
      return 'regional-energy-potential:' + mapStateKey + ':' + kind;
    }}

    function applyResetToken() {{
      if (!viewStorage || !mapStateKey) {{
        return false;
      }}
      const tokenKey = storageKey('reset-token');
      const previousToken = viewStorage.getItem(tokenKey);
      if (previousToken !== String(mapResetToken)) {{
        viewStorage.removeItem(storageKey('view'));
        viewStorage.removeItem(storageKey('overlays'));
        viewStorage.setItem(tokenKey, String(mapResetToken));
        return true;
      }}
      return false;
    }}

    const resetRequested = applyResetToken();

    function readSavedView() {{
      if (!viewStorage || !mapStateKey || resetRequested) {{
        return null;
      }}
      try {{
        const raw = viewStorage.getItem(storageKey('view'));
        if (!raw) {{
          return null;
        }}
        const parsed = JSON.parse(raw);
        const lat = Number(parsed.lat);
        const lng = Number(parsed.lng);
        const viewZoom = Number(parsed.zoom);
        if (
          Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(viewZoom) &&
          lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 &&
          viewZoom >= 0 && viewZoom <= 22
        ) {{
          return {{ lat, lng, zoom: viewZoom }};
        }}
      }} catch (err) {{}}
      return null;
    }}

    function readSavedOverlayVisibility() {{
      if (!viewStorage || !mapStateKey) {{
        return null;
      }}
      try {{
        const raw = viewStorage.getItem(storageKey('overlays'));
        if (!raw) {{
          return null;
        }}
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') {{
          return null;
        }}
        return parsed;
      }} catch (err) {{}}
      return null;
    }}

    function storeMapView() {{
      if (!viewStorage || !mapStateKey) {{
        return;
      }}
      const currentCenter = map.getCenter();
      viewStorage.setItem(
        storageKey('view'),
        JSON.stringify({{
          lat: currentCenter.lat,
          lng: currentCenter.lng,
          zoom: map.getZoom()
        }})
      );
    }}

    const savedView = readSavedView();
    const savedOverlayVisibility = readSavedOverlayVisibility();
    const mapStartCenter = savedView ? [savedView.lat, savedView.lng] : defaultCenter;
    const mapStartZoom = savedView ? savedView.zoom : {int(zoom)};
    const map = L.map('map', {{ preferCanvas: true }}).setView(mapStartCenter, mapStartZoom);

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function clamp01(value, fallbackValue) {{
      const parsed = Number(value);
      if (!Number.isFinite(parsed)) {{
        return fallbackValue;
      }}
      return Math.max(0.0, Math.min(1.0, parsed));
    }}

    function firstFiniteNumber(values, fallbackValue) {{
      for (const value of values) {{
        const parsed = Number(value);
        if (Number.isFinite(parsed)) {{
          return parsed;
        }}
      }}
      return fallbackValue;
    }}

    function layerFillOpacity(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      const defaultOpacity = spec.layer_kind === 'vector' ? 1.0 : 0.78;
      let baseOpacity = spec.fill_opacity != null ? clamp01(spec.fill_opacity, defaultOpacity) : defaultOpacity;
      if (spec.fill_opacity_property && props[spec.fill_opacity_property] != null) {{
        baseOpacity = clamp01(props[spec.fill_opacity_property], defaultOpacity);
      }}
      if (spec.layer_kind === 'vector') {{
        return clamp01(baseOpacity * vectorLayerOpacity, vectorLayerOpacity);
      }}
      return baseOpacity;
    }}

    function layerFillColor(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (spec.fill_property && props[spec.fill_property]) {{
        return props[spec.fill_property];
      }}
      return spec.fill_color || props.fill || props.cluster_fill || props.factor_fill || '#999999';
    }}

    function layerStrokeColor(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (spec.stroke_property && props[spec.stroke_property]) {{
        return props[spec.stroke_property];
      }}
      return spec.stroke_color || '#555555';
    }}

    function layerStrokeWeight(spec, feature, isPointLayer) {{
      const props = (feature && feature.properties) || {{}};
      const featureValue = spec.stroke_weight_property ? Number(props[spec.stroke_weight_property]) : NaN;
      const parsed = Number.isFinite(featureValue) ? featureValue : Number(spec.weight);
      if (Number.isFinite(parsed)) {{
        return isPointLayer ? Math.max(parsed, 1.0) : parsed;
      }}
      return isPointLayer ? 1.0 : 0.25;
    }}

    function layerStrokeOpacity(spec, fillOpacity) {{
      const defaultOpacity = Math.min(0.85, fillOpacity + 0.1);
      const baseOpacity = spec.stroke_opacity != null
        ? clamp01(spec.stroke_opacity, defaultOpacity)
        : defaultOpacity;
      if (spec.layer_kind === 'vector') {{
        return clamp01(baseOpacity * vectorLayerOpacity, baseOpacity);
      }}
      if (spec.stroke_opacity != null) {{
        return clamp01(spec.stroke_opacity, defaultOpacity);
      }}
      return defaultOpacity;
    }}

    function layerStrokeEnabled(spec, strokeWeight, strokeOpacity) {{
      if (spec.stroke === false) {{
        return false;
      }}
      return strokeWeight > 0.01 && strokeOpacity > 0.01;
    }}

    function layerPointRadiusMetersAtScale(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      const radius = firstFiniteNumber([props.point_radius_m_at_scale, spec.point_radius_m_at_scale], NaN);
      return Number.isFinite(radius) && radius > 0 ? radius : null;
    }}

    function layerPointRadiusPixels(spec, feature, latlng) {{
      const props = (feature && feature.properties) || {{}};
      const fallbackRadius = firstFiniteNumber([props.point_radius, spec.point_radius], 4.0);
      const radiusMeters = layerPointRadiusMetersAtScale(spec, feature);
      if (radiusMeters === null) {{
        return fallbackRadius;
      }}
      const lat = Number.isFinite(Number(latlng && latlng.lat)) ? Number(latlng.lat) : Number(map.getCenter().lat);
      const cosLat = Math.max(0.05, Math.cos(lat * Math.PI / 180.0));
      const metersPerPixel = Math.max(0.0001, (40075016.686 * cosLat) / Math.pow(2, map.getZoom() + 8));
      const minRadius = Math.max(0.5, firstFiniteNumber([props.point_min_radius, spec.point_min_radius], 2.2));
      const maxRadius = Math.max(minRadius, firstFiniteNumber([props.point_max_radius, spec.point_max_radius], 4.6));
      return Math.max(minRadius, Math.min(maxRadius, radiusMeters / metersPerPixel));
    }}

    function popupHtml(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (props.popup) {{
        return props.popup;
      }}
      const title = props.tooltip_title || props.layer_label || spec.name;
      const body = props.tooltip_body || '';
      return body ? ('<strong>' + title + '</strong><br>' + body) : (props.hex_id || title);
    }}

    const overlays = {{}};
    const renderedLayers = [];
    const layerRecords = [];
    const legendSourceRecords = [];
    const scalablePointMarkers = [];
    const autoFamilies = {{}};

    function buildGeoJsonLayer(spec, index) {{
      const paneName = 'overlay-pane-' + index;
      const pane = map.createPane(paneName);
      const zIndex = Number.isFinite(Number(spec.z_index)) ? Number(spec.z_index) : (400 + index);
      pane.style.zIndex = String(zIndex);

      return L.geoJSON(spec.feature_collection, {{
        pane: paneName,
        style: function(feature) {{
          const fillOpacity = layerFillOpacity(spec, feature);
          const strokeWeight = layerStrokeWeight(spec, feature, false);
          const strokeOpacity = layerStrokeOpacity(spec, fillOpacity);
          const strokeEnabled = layerStrokeEnabled(spec, strokeWeight, strokeOpacity);
          return {{
            stroke: strokeEnabled,
            color: layerStrokeColor(spec, feature),
            weight: strokeEnabled ? strokeWeight : 0,
            opacity: strokeEnabled ? strokeOpacity : 0,
            dashArray: spec.dash_array || null,
            fillColor: layerFillColor(spec, feature),
            fillOpacity: fillOpacity
          }};
        }},
        pointToLayer: function(feature, latlng) {{
          const fillOpacity = layerFillOpacity(spec, feature);
          const strokeWeight = layerStrokeWeight(spec, feature, true);
          const strokeOpacity = layerStrokeOpacity(spec, fillOpacity);
          const strokeEnabled = layerStrokeEnabled(spec, strokeWeight, strokeOpacity);
          const marker = L.circleMarker(latlng, {{
            radius: layerPointRadiusPixels(spec, feature, latlng),
            pane: paneName,
            stroke: strokeEnabled,
            color: layerStrokeColor(spec, feature),
            weight: strokeEnabled ? strokeWeight : 0,
            opacity: strokeEnabled ? strokeOpacity : 0,
            dashArray: spec.dash_array || null,
            fillColor: layerFillColor(spec, feature),
            fillOpacity: Math.max(fillOpacity, 0.22)
          }});
          if (layerPointRadiusMetersAtScale(spec, feature) !== null) {{
            scalablePointMarkers.push({{ marker, spec, feature, latlng }});
          }}
          return marker;
        }},
        onEachFeature: function(feature, itemLayer) {{
          const props = (feature && feature.properties) || {{}};
          if (props.tooltip_title || props.tooltip_body) {{
            const tooltipTitle = props.tooltip_title || props.hex_id || spec.name;
            const tooltipBody = props.tooltip_body || '';
            itemLayer.bindTooltip(
              tooltipBody ? ('<strong>' + tooltipTitle + '</strong><br>' + tooltipBody) : tooltipTitle,
              {{ sticky: true, direction: 'top', opacity: 0.92 }}
            );
          }}
          itemLayer.bindPopup(popupHtml(spec, feature));
        }}
      }});
    }}

    function refreshScalablePointMarkers() {{
      scalablePointMarkers.forEach(function(record) {{
        record.marker.setRadius(layerPointRadiusPixels(record.spec, record.feature, record.latlng));
      }});
    }}

    layerSpecs.forEach(function(spec, index) {{
      const layer = buildGeoJsonLayer(spec, index);
      renderedLayers.push(layer);
      if (spec.legend_items && spec.legend_items.length > 0) {{
        legendSourceRecords.push({{ spec, layer }});
      }}

      const autoGroupId = spec.auto_resolution_group || '';
      if (autoGroupId) {{
        if (!autoFamilies[autoGroupId]) {{
          autoFamilies[autoGroupId] = {{
            id: autoGroupId,
            controlName: spec.control_name || spec.name,
            selectedResolution: Number(spec.selected_resolution),
            lockSelectedResolution: Boolean(spec.lock_selected_resolution),
            defaultVisible: spec.default_visible !== false,
            controller: L.layerGroup(),
            activeResolution: null,
            activeLayer: null,
            layers: []
          }};
        }}
        autoFamilies[autoGroupId].layers.push({{
          resolution: Number(spec.auto_resolution),
          minZoom: Number.isFinite(Number(spec.auto_min_zoom)) ? Number(spec.auto_min_zoom) : 0,
          layer: layer
        }});
        return;
      }}

      overlays[spec.name] = layer;
      layerRecords.push({{ name: spec.name, layer: layer, spec: spec }});
      const shouldShow = savedOverlayVisibility && Object.prototype.hasOwnProperty.call(savedOverlayVisibility, spec.name)
        ? Boolean(savedOverlayVisibility[spec.name])
        : (spec.default_visible !== false);
      if (shouldShow) {{
        layer.addTo(map);
      }}
    }});

    const autoFamilyRecords = Object.values(autoFamilies);

    function roundScaleValue(num) {{
      const digits = Math.pow(10, String(Math.floor(num)).length - 1);
      const normalized = num / digits;
      let rounded = digits;
      if (normalized >= 10) {{
        rounded = 10 * digits;
      }} else if (normalized >= 5) {{
        rounded = 5 * digits;
      }} else if (normalized >= 3) {{
        rounded = 3 * digits;
      }} else if (normalized >= 2) {{
        rounded = 2 * digits;
      }}
      return rounded;
    }}

    function currentMetricScaleValue() {{
      const maxWidth = 160;
      const centerY = map.getSize().y / 2;
      const leftPoint = map.containerPointToLatLng([0, centerY]);
      const rightPoint = map.containerPointToLatLng([maxWidth, centerY]);
      const maxMeters = map.distance(leftPoint, rightPoint);
      if (!Number.isFinite(maxMeters) || maxMeters <= 0) {{
        return 0;
      }}
      return roundScaleValue(maxMeters);
    }}

    function autoResolutionFromScale(selectedResolution, scaleMeters) {{
      let desiredResolution = 10;
      if (scaleMeters >= 100000) {{
        desiredResolution = 5;
      }} else if (scaleMeters >= 50000) {{
        desiredResolution = 6;
      }} else if (scaleMeters >= 30000) {{
        desiredResolution = 7;
      }} else if (scaleMeters >= 10000) {{
        desiredResolution = 8;
      }} else if (scaleMeters >= 5000) {{
        desiredResolution = 9;
      }}
      return Math.min(Number(selectedResolution), desiredResolution);
    }}

    function desiredAutoFamilyEntry(family) {{
      const sortedLayers = family.layers
        .slice()
        .sort(function(left, right) {{ return right.resolution - left.resolution; }});
      if (sortedLayers.length === 0) {{
        return null;
      }}

      if (family.lockSelectedResolution) {{
        const locked = sortedLayers.find(function(entry) {{ return entry.resolution === family.selectedResolution; }});
        return locked || sortedLayers[0];
      }}

      const selectedResolution = Number.isFinite(family.selectedResolution)
        ? family.selectedResolution
        : sortedLayers[0].resolution;
      const scaleMeters = currentMetricScaleValue();
      const desiredResolution = autoResolutionFromScale(selectedResolution, scaleMeters);
      const eligible = sortedLayers.filter(function(entry) {{ return entry.resolution <= desiredResolution; }});
      const candidates = eligible.length > 0 ? eligible : sortedLayers;
      return candidates[0] || sortedLayers[sortedLayers.length - 1];
    }}

    function syncAutoFamily(family) {{
      const desired = desiredAutoFamilyEntry(family);
      if (!desired) {{
        return;
      }}

      if (family.activeLayer && family.activeLayer !== desired.layer) {{
        family.controller.removeLayer(family.activeLayer);
      }}

      family.activeLayer = desired.layer;
      family.activeResolution = desired.resolution;

      if (!map.hasLayer(family.controller)) {{
        family.controller.clearLayers();
        return;
      }}

      if (!family.controller.hasLayer(desired.layer)) {{
        family.controller.clearLayers();
        family.controller.addLayer(desired.layer);
      }}
    }}

    autoFamilyRecords.forEach(function(family) {{
      overlays[family.controlName] = family.controller;
      layerRecords.push({{ name: family.controlName, layer: family.controller, family: family }});
      const shouldShow = savedOverlayVisibility && Object.prototype.hasOwnProperty.call(savedOverlayVisibility, family.controlName)
        ? Boolean(savedOverlayVisibility[family.controlName])
        : family.defaultVisible;
      if (shouldShow) {{
        family.controller.addTo(map);
        syncAutoFamily(family);
      }}
    }});

    L.control.layers({{ 'OSM': osm, 'Satellite': satellite }}, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    function storeOverlayVisibility() {{
      if (!viewStorage || !mapStateKey) {{
        return;
      }}
      const payload = {{}};
      layerRecords.forEach(function(record) {{
        payload[record.name] = map.hasLayer(record.layer);
      }});
      viewStorage.setItem(storageKey('overlays'), JSON.stringify(payload));
    }}
    map.on('overlayadd', function(event) {{
      autoFamilyRecords.forEach(function(family) {{
        if (event.layer === family.controller) {{
          syncAutoFamily(family);
        }}
      }});
      storeOverlayVisibility();
      updateLegendContent();
    }});
    map.on('overlayremove', function(event) {{
      autoFamilyRecords.forEach(function(family) {{
        if (event.layer === family.controller) {{
          family.controller.clearLayers();
        }}
      }});
      storeOverlayVisibility();
      updateLegendContent();
    }});
    map.on('moveend', storeMapView);
    map.on('zoomend', function() {{
      autoFamilyRecords.forEach(syncAutoFamily);
      refreshScalablePointMarkers();
      storeMapView();
    }});
    storeOverlayVisibility();

    function recordLayerFeatureCount(layer) {{
      if (!layer || typeof layer.getLayers !== 'function') {{
        return 0;
      }}
      const children = layer.getLayers();
      if (!children || children.length === 0) {{
        return 0;
      }}
      return children.reduce(function(total, child) {{
        if (child && typeof child.getLayers === 'function') {{
          return total + recordLayerFeatureCount(child);
        }}
        return total + 1;
      }}, 0);
    }}

    function setOverlayVisibilityByName(name, visible) {{
      const wanted = String(name || '');
      const record = layerRecords.find(function(item) {{ return item.name === wanted; }});
      if (!record) {{
        return false;
      }}
      const shouldShow = Boolean(visible);
      if (shouldShow && !map.hasLayer(record.layer)) {{
        record.layer.addTo(map);
      }} else if (!shouldShow && map.hasLayer(record.layer)) {{
        map.removeLayer(record.layer);
      }}
      if (record.family) {{
        if (shouldShow) {{
          syncAutoFamily(record.family);
        }} else {{
          record.family.controller.clearLayers();
        }}
      }}
      storeOverlayVisibility();
      updateLegendContent();
      return true;
    }}

    window.__potentialMapSetOverlayVisibility = setOverlayVisibilityByName;
    window.__potentialMapOverlayVisible = function(name) {{
      const wanted = String(name || '');
      const record = layerRecords.find(function(item) {{ return item.name === wanted; }});
      return Boolean(record && map.hasLayer(record.layer));
    }};
    window.__potentialMapOverlayKnown = function(name) {{
      const wanted = String(name || '');
      return Boolean(layerRecords.find(function(item) {{ return item.name === wanted; }}));
    }};
    window.__potentialMapOverlayFeatureCount = function(name) {{
      const wanted = String(name || '');
      const record = layerRecords.find(function(item) {{ return item.name === wanted; }});
      return record ? recordLayerFeatureCount(record.layer) : 0;
    }};

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + noteTitle + '</strong><br>' + noteBody;
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    let legendDiv = null;
    const legendById = {{}};
    legendSourceRecords.forEach(function(record) {{
      const spec = record.spec || {{}};
      const autoGroupId = spec.auto_resolution_group || '';
      const visible = autoGroupId && autoFamilies[autoGroupId]
        ? map.hasLayer(autoFamilies[autoGroupId].controller)
        : map.hasLayer(record.layer);
      if (!visible) {{
        return;
      }}
      if (!(spec.legend_items && spec.legend_items.length > 0)) {{
        return;
      }}
      const legendId = spec.legend_id || spec.name;
      if (!legendById[legendId]) {{
        legendById[legendId] = {{
          title: spec.legend_title || spec.name,
          items: spec.legend_items
        }};
      }}
    }});
    const legendSections = Object.values(legendById);
    if (legendSourceRecords.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        legendDiv = div;
        let html = '<div class="map-legend-title">Teckenförklaring</div>';
        legendSections.forEach(function(section) {{
          html += '<div class="map-legend-section">' + section.title + '</div>';
          html += section.items.map(function(item) {{
            const shapeClass = item.shape === 'circle' ? ' circle' : '';
            return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
          }}).join('');
        }});
        div.innerHTML = html;
        L.DomEvent.disableClickPropagation(div);
        updateLegendContent();
        return div;
      }};
      legend.addTo(map);
      updateLegendContent();
    }}

    function updateLegendContent() {{
      if (!legendDiv) {{
        return;
      }}
      const activeLegendById = {{}};
      legendSourceRecords.forEach(function(record) {{
        const spec = record.spec || {{}};
        const autoGroupId = spec.auto_resolution_group || '';
        const visible = autoGroupId && autoFamilies[autoGroupId]
          ? map.hasLayer(autoFamilies[autoGroupId].controller)
          : map.hasLayer(record.layer);
        if (!visible || !(spec.legend_items && spec.legend_items.length > 0)) {{
          return;
        }}
        const legendId = spec.legend_id || spec.control_name || spec.name;
        if (!activeLegendById[legendId]) {{
          activeLegendById[legendId] = {{
            title: spec.legend_title || spec.control_name || spec.name,
            items: spec.legend_items
          }};
        }}
      }});
      const activeLegendSections = Object.values(activeLegendById);
      if (activeLegendSections.length === 0) {{
        legendDiv.style.display = 'none';
        legendDiv.innerHTML = '';
        return;
      }}
      legendDiv.style.display = '';
      let html = '<div class="map-legend-title">Teckenförklaring</div>';
      activeLegendSections.forEach(function(section) {{
        html += '<div class="map-legend-section">' + section.title + '</div>';
        html += section.items.map(function(item) {{
          const shapeClass = item.shape === 'circle' ? ' circle' : '';
          return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
        }}).join('');
      }});
      legendDiv.innerHTML = html;
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (savedView) {{
        storeMapView();
        return;
      }}
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        storeMapView();
        return;
      }}
      const group = L.featureGroup(renderedLayers);
      const dataBounds = group.getBounds();
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
      storeMapView();
    }}
    setTimeout(function() {{
      fitInitialBounds();
      refreshScalablePointMarkers();
    }}, 80);
  </script>
</body>
</html>
"""


def build_potential_map_html(
    feature_collection: dict[str, Any],
    center: list[float],
    zoom: int,
    title: str,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.78,
    legend_items: list[dict[str, str]] | None = None,
) -> str:
    payload = json.dumps(feature_collection, ensure_ascii=False)
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    title_payload = json.dumps(title, ensure_ascii=False)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    legend_payload = json.dumps(legend_items or [], ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note {{ background: rgba(255,255,255,0.94); padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 260px; }}
    .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); line-height: 1.25; max-width: 260px; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 6px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {payload};
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const mapTitle = {title_payload};
    const hexFillOpacity = {opacity_payload};
    const legendItems = {legend_payload};
    const map = L.map('map', {{ preferCanvas: true }}).setView(defaultCenter, {int(zoom)});

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function styleFeature(feature) {{
      const props = feature.properties || {{}};
      return {{
        color: '#555555',
        weight: 0.25,
        opacity: Math.min(0.85, hexFillOpacity + 0.1),
        fillColor: props.fill || '#999999',
        fillOpacity: hexFillOpacity
      }};
    }}

    const potential = L.geoJSON(data, {{
      style: styleFeature,
      onEachFeature: function(feature, layer) {{
        const props = feature.properties || {{}};
        layer.bindPopup(props.popup || props.hex_id || mapTitle);
      }}
    }}).addTo(map);

    const overlays = {{}};
    overlays[mapTitle] = potential;
    L.control.layers({{ 'OSM': osm, 'Satellite': satellite }}, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + mapTitle + '</strong><br>Manifestdriven H3-kapacitetsmodell. Detaljerade vektorer kopplas in senare.';
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    if (legendItems.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = '<div class="map-legend-title">' + mapTitle + '</div>' +
          legendItems.map(function(item) {{
            const shapeClass = item.shape === 'circle' ? ' circle' : '';
            return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
          }}).join('');
        L.DomEvent.disableClickPropagation(div);
        return div;
      }};
      legend.addTo(map);
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        return;
      }}
      const dataBounds = potential.getBounds();
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
    }}
    setTimeout(fitInitialBounds, 80);
  </script>
</body>
</html>
"""
