from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from gcli.cache import build_artifact_id, load_artifact_reference
from gcli.command_meta import CommandInput, CommandSpec, command_contract

console = Console()

VISUALIZE_COMMAND_SPEC = CommandSpec(
    command="gcli tools visualize",
    interactive=False,
    inputs=(
        CommandInput(name="input_artifact", required=False, source="artifact"),
        CommandInput(name="output", required=False, source="default"),
    ),
    outputs=("html_file",),
)

# ---------------------------------------------------------------------------
# HTML template
# Regular string (NOT an f-string) so { } in CSS/JS need no escaping.
# Two unique sentinels are substituted at render time:
#   __GCLI_TITLE__    ← page title
#   __GCLI_ELEMENTS__ ← JSON array of Cytoscape elements
# ---------------------------------------------------------------------------
_GRAPH_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__GCLI_TITLE__</title>
  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }

    /* ── Graph canvas ─────────────────────────────────────────────── */
    #cy {
      position: fixed; top: 0; left: 0;
      width: 100vw; height: 100vh;
      background: #f8f9fa;
      transition: width 0.3s cubic-bezier(0.4,0,0.2,1);
    }
    body.panel-open #cy { width: calc(100vw - 440px); }

    /* ── Gmail icon overlay (shown on node hover) ─────────────────── */
    #node-overlay {
      position: fixed; z-index: 500;
      display: none; pointer-events: none;
    }
    #gmail-icon-btn {
      display: flex; align-items: center; justify-content: center;
      width: 28px; height: 28px;
      background: #fff;
      border-radius: 50%;
      box-shadow: 0 2px 8px rgba(0,0,0,0.28);
      cursor: pointer; pointer-events: all;
      text-decoration: none;
      transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    #gmail-icon-btn:hover { transform: scale(1.18); box-shadow: 0 4px 14px rgba(0,0,0,0.38); }
    #gmail-icon-btn svg { display: block; pointer-events: none; }

    /* ── Detail panel ─────────────────────────────────────────────── */
    #detail-panel {
      position: fixed; top: 0; right: 0;
      width: 440px; height: 100vh;
      background: #fff;
      box-shadow: -3px 0 20px rgba(0,0,0,0.13);
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.4,0,0.2,1);
      z-index: 300;
      display: flex; flex-direction: column; overflow: hidden;
    }
    #detail-panel.open { transform: translateX(0); }

    .panel-hdr {
      background: linear-gradient(135deg, #1f77b4 0%, #145a8f 100%);
      color: #fff; padding: 18px 18px 14px; flex-shrink: 0;
    }
    .panel-hdr-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 11px; }
    .panel-email-wrap { flex: 1; min-width: 0; }
    .panel-email {
      font-size: 13.5px; font-weight: 700;
      word-break: break-all; cursor: pointer;
      border-radius: 4px; padding: 2px 5px; margin: -2px -5px;
      line-height: 1.4; transition: background 0.1s;
    }
    .panel-email:hover { background: rgba(255,255,255,0.18); }
    .panel-copy-hint { font-size: 10px; opacity: 0.6; margin-top: 3px; padding-left: 5px; }
    .panel-close {
      flex-shrink: 0; background: rgba(255,255,255,0.18); border: none; color: #fff;
      width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
      font-size: 15px; display: flex; align-items: center; justify-content: center;
      transition: background 0.12s; line-height: 1;
    }
    .panel-close:hover { background: rgba(255,255,255,0.32); }
    .panel-gmail-btn {
      display: inline-flex; align-items: center; gap: 6px;
      background: rgba(255,255,255,0.94); color: #1a5c8a;
      border: none; border-radius: 20px; padding: 5px 14px;
      font-size: 12px; font-weight: 700; cursor: pointer;
      text-decoration: none; transition: background 0.12s;
    }
    .panel-gmail-btn:hover { background: #fff; }
    .panel-meta {
      display: flex; flex-wrap: wrap; gap: 8px 18px;
      margin-top: 10px; font-size: 11px; opacity: 0.82;
    }
    .panel-meta-item { display: flex; align-items: center; gap: 4px; }

    .panel-body { flex: 1; overflow-y: auto; overscroll-behavior: contain; }
    .panel-section { padding: 14px 18px; border-bottom: 1px solid #f0f0f0; }
    .section-title {
      font-size: 10.5px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.9px; color: #aaa; margin-bottom: 10px;
    }

    /* Context snippet */
    .snippet-box {
      background: #f6f8fa; border: 1px solid #e9ecef; border-radius: 6px;
      padding: 10px 12px; font-size: 12px; line-height: 1.6; color: #444;
      font-family: 'Consolas', 'SFMono-Regular', monospace;
      white-space: pre-wrap; word-break: break-word;
    }
    .snippet-highlight {
      background: #fff3cd; border-radius: 3px;
      padding: 0 3px; font-weight: 700; color: #7a5c00;
    }

    /* Occurrences table */
    .occ-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .occ-table th {
      background: #f6f8fa; padding: 7px 8px; text-align: left;
      font-weight: 600; color: #666; border-bottom: 2px solid #e9ecef; white-space: nowrap;
    }
    .occ-table td {
      padding: 7px 8px; border-bottom: 1px solid #f3f3f3; color: #333;
      vertical-align: middle; max-width: 130px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .occ-table tr:hover td { background: #f8f9fa; }
    .msg-id { font-family: 'Consolas', monospace; font-size: 11px; color: #666; }
    .badge {
      display: inline-block; padding: 2px 7px; border-radius: 10px;
      font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
    }
    .badge-sent     { background: #d4edda; color: #155724; }
    .badge-mentions { background: #fff3cd; color: #856404; }
    .open-link {
      display: inline-flex; align-items: center; justify-content: center;
      width: 24px; height: 24px; background: #e8f0fe; border-radius: 50%;
      text-decoration: none; font-size: 13px; font-weight: 700; color: #1f77b4;
      transition: background 0.12s, color 0.12s;
    }
    .open-link:hover { background: #1f77b4; color: #fff; }
    .no-occs { font-size: 12.5px; color: #999; padding: 6px 0; line-height: 1.5; }
    .view-all-btn {
      display: block; width: 100%; margin-top: 10px; padding: 9px;
      background: #f0f7ff; border: 1.5px dashed #b3d1f0; border-radius: 6px;
      color: #1f77b4; font-size: 12px; font-weight: 700; cursor: pointer;
      text-align: center; transition: background 0.12s, border-color 0.12s;
    }
    .view-all-btn:hover { background: #e0edff; border-color: #1f77b4; }

    /* ── Full occurrences screen ──────────────────────────────────── */
    #full-occurrences {
      position: fixed; inset: 0; background: #fff;
      z-index: 600; display: none; flex-direction: column;
    }
    #full-occurrences.open { display: flex; }
    .full-hdr {
      background: linear-gradient(135deg, #1f77b4 0%, #145a8f 100%);
      color: #fff; padding: 14px 22px;
      display: flex; align-items: center; gap: 14px; flex-shrink: 0;
    }
    .full-back-btn {
      background: rgba(255,255,255,0.18); border: none; color: #fff;
      padding: 5px 14px; border-radius: 20px; cursor: pointer;
      font-size: 12.5px; font-weight: 700; white-space: nowrap;
      transition: background 0.12s;
    }
    .full-back-btn:hover { background: rgba(255,255,255,0.32); }
    .full-hdr-email { font-size: 15px; font-weight: 700; word-break: break-all; }
    .full-hdr-count { font-size: 12px; opacity: 0.72; margin-top: 2px; }
    .full-body { flex: 1; overflow: auto; padding: 20px 24px; }
    .full-occ-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .full-occ-table th {
      background: #f6f8fa; padding: 9px 12px; text-align: left;
      font-weight: 700; color: #444; border-bottom: 2px solid #dee2e6;
      position: sticky; top: 0; white-space: nowrap;
    }
    .full-occ-table td {
      padding: 9px 12px; border-bottom: 1px solid #f0f0f0;
      color: #333; vertical-align: middle;
    }
    .full-occ-table tr:hover td { background: #f8f9fa; }
    .row-num { color: #ccc; font-size: 12px; text-align: right; }

    /* ── Toast ────────────────────────────────────────────────────── */
    #toast {
      position: fixed; bottom: 22px; left: 50%;
      transform: translateX(-50%) translateY(70px);
      background: rgba(28,28,28,0.9); color: #fff;
      padding: 7px 18px; border-radius: 20px; font-size: 13px;
      z-index: 900; transition: transform 0.2s ease;
      pointer-events: none; white-space: nowrap;
    }
    #toast.show { transform: translateX(-50%) translateY(0); }
  </style>
</head>
<body>
  <div id="cy"></div>

  <!-- Gmail icon overlay (shown on node hover) -->
  <div id="node-overlay">
    <a id="gmail-icon-btn" href="#" target="_blank" title="Open this email in Gmail">
      <svg viewBox="0 0 24 24" width="16" height="16" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9
                 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z" fill="#EA4335"/>
      </svg>
    </a>
  </div>

  <!-- Right-side detail panel -->
  <div id="detail-panel">
    <div class="panel-hdr">
      <div class="panel-hdr-row">
        <div class="panel-email-wrap">
          <div class="panel-email" id="panel-email" title="Click to copy"></div>
          <div class="panel-copy-hint">&#8593; click to copy</div>
        </div>
        <button class="panel-close" id="panel-close" title="Close">&#x2715;</button>
      </div>
      <a class="panel-gmail-btn" id="panel-gmail-btn" href="#" target="_blank">
        <svg viewBox="0 0 24 24" width="13" height="13">
          <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9
                   2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z" fill="#EA4335"/>
        </svg>
        Open in Gmail
      </a>
      <div class="panel-meta" id="panel-meta"></div>
    </div>
    <div class="panel-body">
      <div class="panel-section">
        <div class="section-title">Context</div>
        <div class="snippet-box" id="panel-context"></div>
      </div>
      <div class="panel-section">
        <div class="section-title">Occurrences</div>
        <div id="panel-occurrences"></div>
      </div>
    </div>
  </div>

  <!-- Full occurrences screen -->
  <div id="full-occurrences">
    <div class="full-hdr">
      <button class="full-back-btn" id="full-back-btn">&#8592; Back</button>
      <div>
        <div class="full-hdr-email" id="full-hdr-email"></div>
        <div class="full-hdr-count" id="full-hdr-count"></div>
      </div>
    </div>
    <div class="full-body">
      <table class="full-occ-table">
        <thead>
          <tr>
            <th style="width:32px">#</th>
            <th>Email ID</th>
            <th>From</th>
            <th>To</th>
            <th>Type</th>
            <th>Source</th>
            <th>Timestamp</th>
            <th style="width:48px"></th>
          </tr>
        </thead>
        <tbody id="full-occ-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Toast notification -->
  <div id="toast"></div>

  <script>
    const elements = __GCLI_ELEMENTS__;

    // ── Helpers ──────────────────────────────────────────────────────
    function makeGmailLink(msgId, email) {
      if (msgId) return 'https://mail.google.com/mail/u/0/#all/' + msgId;
      return 'https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(email);
    }
    function formatTs(ts) {
      if (!ts) return '\u2014';
      try {
        var d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        return d.toLocaleDateString('en-US', {year:'numeric', month:'short', day:'numeric'});
      } catch(e) { return ts; }
    }
    function truncate(s, n) {
      if (s == null || s === '') return '\u2014';
      return s.length > n ? s.slice(0, n) + '\u2026' : s;
    }
    function escHtml(s) {
      if (s == null) return '';
      return ('' + s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function showToast(msg) {
      var t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(function() { t.classList.remove('show'); }, 2000);
    }

    // ── Cytoscape ────────────────────────────────────────────────────
    var cy = cytoscape({
      container: document.getElementById('cy'),
      elements: elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': '#1f77b4',
            'color': '#111',
            'font-size': 'mapData(degree, 0, 10, 11, 15)',
            'text-wrap': 'wrap',
            'text-max-width': '180px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': '8px',
            'width': 'data(size)',
            'height': 'data(size)',
            'border-width': 2,
            'border-color': 'rgba(255,255,255,0.35)',
            'transition-property': 'opacity, border-width, border-color, background-color',
            'transition-duration': '180ms'
          }
        },
        {
          selector: 'node.node-selected',
          style: {
            'border-width': 4,
            'border-color': '#ff6b35',
            'background-color': '#2196f3'
          }
        },
        { selector: 'node.node-dimmed', style: { 'opacity': 0.15 } },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'line-color': '#aaa',
            'target-arrow-color': '#aaa',
            'label': 'data(type)',
            'font-size': '10px',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.9,
            'text-background-padding': '3px',
            'text-opacity': 0,     /* hidden by default */
            'opacity': 0.55,
            'transition-property': 'opacity',
            'transition-duration': '0ms'   /* immediate on hover */
          }
        },
        {
          selector: 'edge.edge-hovered',
          style: { 'text-opacity': 1, 'opacity': 1, 'z-index': 10 }
        },
        {
          selector: 'edge.edge-highlighted',
          style: { 'opacity': 1 }
        },
        { selector: 'edge.edge-dimmed', style: { 'opacity': 0.07 } },
        {
          selector: 'edge[type = "SENT_TO"]',
          style: { 'line-color': '#2ca02c', 'target-arrow-color': '#2ca02c' }
        },
        {
          selector: 'edge[type = "MENTIONS"]',
          style: { 'line-color': '#ff7f0e', 'target-arrow-color': '#ff7f0e' }
        }
      ],
      layout: {
        name: 'cose',
        animate: false,
        idealEdgeLength: 280,       /* was 200 — more spacing */
        nodeRepulsion: 2500000,     /* was 1200000 — more spacing */
        nodeOverlap: 80,            /* was 60 */
        gravity: 0.15,
        numIter: 2000,
        coolingFactor: 0.995,
        minTemp: 1.0,
        padding: 80
      }
    });

    cy.on('layoutstop', function() {
      var maxIter = Math.max(3, Math.min(8, Math.floor(600 / (cy.nodes().length || 1))));
      resolveOverlaps(cy, maxIter);
    });

    function resolveOverlaps(cy, iterations) {
      var nodes = cy.nodes();
      for (var iter = 0; iter < iterations; iter++) {
        var moved = false;
        for (var i = 0; i < nodes.length; i++) {
          for (var j = i + 1; j < nodes.length; j++) {
            var a = nodes[i], b = nodes[j];
            var posA = a.position(), posB = b.position();
            var sizeA = (a.data('size') || 30) / 2;
            var sizeB = (b.data('size') || 30) / 2;
            var minDist = sizeA + sizeB + 60;
            var dx = posB.x - posA.x, dy = posB.y - posA.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
            if (dist < minDist) {
              var overlap = minDist - dist;
              var degA = a.data('degree') || 0, degB = b.data('degree') || 0;
              var totalDeg = degA + degB + 2;
              var pushA = (degB + 1) / totalDeg, pushB = (degA + 1) / totalDeg;
              var nx = dx / dist, ny = dy / dist;
              a.position({ x: posA.x - nx * overlap * pushA,
                            y: posA.y - ny * overlap * pushA });
              b.position({ x: posB.x + nx * overlap * pushB,
                            y: posB.y + ny * overlap * pushB });
              moved = true;
            }
          }
        }
        if (!moved) break;
      }
      cy.fit(cy.nodes(), 80);
    }

    // ── Gmail icon overlay ────────────────────────────────────────────
    var overlay   = document.getElementById('node-overlay');
    var gmailBtn  = document.getElementById('gmail-icon-btn');
    var hideTimer = null;

    function showOverlay(node) {
      clearTimeout(hideTimer);
      var pos = node.renderedPosition();
      var w   = node.renderedWidth();
      var h   = node.renderedHeight();
      overlay.style.left    = (pos.x + w / 2 - 12) + 'px';
      overlay.style.top     = (pos.y - h / 2 - 14) + 'px';
      overlay.style.display = 'flex';
      gmailBtn.href = makeGmailLink(node.data('primary_ref'), node.id());
    }
    function scheduleHideOverlay() {
      hideTimer = setTimeout(function() {
        if (!overlay.matches(':hover')) overlay.style.display = 'none';
      }, 130);
    }
    overlay.addEventListener('mouseenter', function() { clearTimeout(hideTimer); });
    overlay.addEventListener('mouseleave', scheduleHideOverlay);

    cy.on('mouseover', 'node', function(e) { showOverlay(e.target); });
    cy.on('mouseout',  'node', function()  { scheduleHideOverlay(); });
    cy.on('pan zoom',  function()          { overlay.style.display = 'none'; });
    window.addEventListener('resize',      function() { overlay.style.display = 'none'; });

    // ── Edge labels: hidden by default, shown immediately on hover ────
    cy.on('mouseover', 'edge', function(e) { e.target.addClass('edge-hovered'); });
    cy.on('mouseout',  'edge', function(e) { e.target.removeClass('edge-hovered'); });

    // ── Node tap → detail panel ───────────────────────────────────────
    var activeNode = null;

    cy.on('tap', 'node', function(e) { openPanel(e.target); });
    cy.on('tap', function(e) { if (e.target === cy) closePanel(); });

    function openPanel(node) {
      activeNode = node;
      cy.elements().removeClass(
        'node-selected node-dimmed edge-highlighted edge-dimmed edge-hovered'
      );
      node.addClass('node-selected');
      var connEdges = node.connectedEdges();
      connEdges.addClass('edge-highlighted');
      cy.nodes().not(node).not(node.neighborhood().nodes()).addClass('node-dimmed');
      cy.edges().not(connEdges).addClass('edge-dimmed');

      renderPanel(node);
      document.getElementById('detail-panel').classList.add('open');
      document.body.classList.add('panel-open');
      setTimeout(function() { cy.resize(); }, 320);
    }

    function closePanel() {
      cy.elements().removeClass(
        'node-selected node-dimmed edge-highlighted edge-dimmed'
      );
      activeNode = null;
      document.getElementById('detail-panel').classList.remove('open');
      document.body.classList.remove('panel-open');
      overlay.style.display = 'none';
      setTimeout(function() { cy.resize(); }, 320);
    }

    function renderPanel(node) {
      var email      = node.id();
      var occs       = node.data('occurrences') || [];
      var primaryRef = node.data('primary_ref') || '';
      var degree     = node.data('degree') || 0;

      document.getElementById('panel-email').textContent = email;
      document.getElementById('panel-gmail-btn').href = makeGmailLink(primaryRef, email);

      // Meta bar
      var connEdges = node.connectedEdges();
      var typeSet   = {};
      connEdges.each(function(e) { typeSet[e.data('type')] = true; });
      var types    = Object.keys(typeSet).join(', ') || '\u2014';
      var latestTs = occs.length ? occs[0].timestamp : '';
      document.getElementById('panel-meta').innerHTML =
        '<span class="panel-meta-item">' +
          '<svg viewBox="0 0 24 24" width="11" height="11"'
            + ' style="flex-shrink:0;fill:currentColor">' +
            '<path d="M20 3h-1V1h-2v2H7V1H5v2H4c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2' +
                    'h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 18H4V8h16v13z"/>' +
          '</svg>&nbsp;' + escHtml(latestTs ? formatTs(latestTs) : 'No date') +
        '</span>' +
        '<span class="panel-meta-item">' + escHtml(types) + '</span>' +
        '<span class="panel-meta-item">Degree&nbsp;' + degree + '</span>';

      // Context: show connected edges, highlight the email address
      var lines = [];
      connEdges.each(function(e) {
        lines.push(e.data('type') + ':  ' + e.data('source') + '  \u2192  ' + e.data('target'));
      });
      var ctxText = lines.length
        ? lines.slice(0, 5).join('\\n') + (lines.length > 5 ? '\\n\u2026' : '')
        : 'no direct context available';
      // Highlight the email address in context using split/join (no regex escaping needed)
      var ctxHtml      = escHtml(ctxText);
      var emailHtml    = escHtml(email);
      var highlighted  = '<span class="snippet-highlight">' + emailHtml + '</span>';
      document.getElementById('panel-context').innerHTML =
        ctxHtml.split(emailHtml).join(highlighted);

      // Occurrences preview (up to 5 rows)
      var preview = occs.slice(0, 5);
      var html = '';
      if (preview.length === 0) {
        html = '<div class="no-occs">No message-level occurrences found.<br>' +
               'Re-run the pipeline to populate this data.</div>';
      } else {
        html = '<table class="occ-table"><thead><tr>' +
          '<th>Email ID</th><th>Type</th><th>Related</th><th>Timestamp</th><th></th>' +
          '</tr></thead><tbody>';
        for (var i = 0; i < preview.length; i++) {
          var occ   = preview[i];
          var oLink = escHtml(makeGmailLink(occ.msg_id, email));
          var tCls  = occ.edge_type === 'SENT_TO' ? 'badge-sent' : 'badge-mentions';
          var tLbl  = occ.edge_type === 'SENT_TO' ? 'SENT TO' : 'MENTIONS';
          var rel   = occ.from_email === email ? occ.to_email : occ.from_email;
          html += '<tr>' +
            '<td title="' + escHtml(occ.msg_id) + '"><span class="msg-id">' +
              truncate(occ.msg_id, 12) + '</span></td>' +
            '<td><span class="badge ' + tCls + '">' + tLbl + '</span></td>' +
            '<td title="' + escHtml(rel) + '">' + truncate(rel, 20) + '</td>' +
            '<td>' + formatTs(occ.timestamp) + '</td>' +
            '<td><a href="' + oLink + '" target="_blank" class="open-link"' +
              ' title="Open in Gmail">\u2197</a></td>' +
            '</tr>';
        }
        html += '</tbody></table>';
      }
      if (occs.length > 5) {
        html += '<button class="view-all-btn" id="view-all-btn">' +
                'View all occurrences (' + occs.length + ')</button>';
      }
      document.getElementById('panel-occurrences').innerHTML = html;
      if (occs.length > 5) {
        document.getElementById('view-all-btn').addEventListener('click', function() {
          openFullView(email);
        });
      }
    }

    // Panel controls
    document.getElementById('panel-close').addEventListener('click', closePanel);
    document.getElementById('panel-email').addEventListener('click', function() {
      var text = this.textContent;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() { showToast('Copied!'); });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta);
        ta.select(); document.execCommand('copy');
        document.body.removeChild(ta); showToast('Copied!');
      }
    });

    // ── Full occurrences screen ───────────────────────────────────────
    function openFullView(email) {
      var node = cy.getElementById(email);
      var occs = (node && node.length) ? (node.data('occurrences') || []) : [];
      document.getElementById('full-hdr-email').textContent = email;
      document.getElementById('full-hdr-count').textContent =
        occs.length + ' occurrence' + (occs.length !== 1 ? 's' : '');
      var rows = '';
      for (var i = 0; i < occs.length; i++) {
        var occ   = occs[i];
        var oLink = escHtml(makeGmailLink(occ.msg_id, email));
        var tCls  = occ.edge_type === 'SENT_TO' ? 'badge-sent' : 'badge-mentions';
        var tLbl  = occ.edge_type === 'SENT_TO' ? 'SENT TO' : 'MENTIONS';
        rows += '<tr>' +
          '<td class="row-num">' + (i + 1) + '</td>' +
          '<td><span class="msg-id">' + escHtml(occ.msg_id || '\u2014') + '</span></td>' +
          '<td>' + escHtml(occ.from_email) + '</td>' +
          '<td>' + escHtml(occ.to_email) + '</td>' +
          '<td><span class="badge ' + tCls + '">' + tLbl + '</span></td>' +
          '<td>' + escHtml(occ.content_source || '\u2014') + '</td>' +
          '<td>' + formatTs(occ.timestamp) + '</td>' +
          '<td><a href="' + oLink + '" target="_blank" class="open-link"' +
            ' title="Open in Gmail">\u2197</a></td>' +
          '</tr>';
      }
      document.getElementById('full-occ-tbody').innerHTML = rows;
      document.getElementById('full-occurrences').classList.add('open');
    }

    document.getElementById('full-back-btn').addEventListener('click', function() {
      document.getElementById('full-occurrences').classList.remove('open');
    });
  </script>
</body>
</html>
"""


def _compute_degrees(graph: dict[str, Any]) -> dict[str, int]:
    """Return a mapping of node id -> total degree (in + out)."""
    degree: dict[str, int] = {}
    for edge in graph.get("edges", []):
        for key in ("from", "to"):
            nid = edge.get(key, "")
            if nid:
                degree[nid] = degree.get(nid, 0) + 1
    return degree


def _to_cytoscape_elements(graph: dict[str, Any]) -> list[dict[str, Any]]:
    degree = _compute_degrees(graph)
    max_degree = max(degree.values(), default=1)

    # Build per-node occurrence list from edge source_references
    node_occurrences: dict[str, list[dict[str, Any]]] = {}

    for edge in graph.get("edges", []):
        source = edge.get("from", "")
        target = edge.get("to", "")
        edge_type = edge.get("type", "")
        refs = edge.get("source_references", [])
        timestamps_list = edge.get("timestamps", [])
        content_sources = edge.get("content_sources", [])

        for i, ref in enumerate(refs):
            ts = timestamps_list[i] if i < len(timestamps_list) else (edge.get("timestamp") or "")
            cs = content_sources[i] if i < len(content_sources) else ""
            occ: dict[str, Any] = {
                "msg_id": ref,
                "timestamp": ts,
                "edge_type": edge_type,
                "from_email": source,
                "to_email": target,
                "content_source": cs,
            }
            for node_email in (source, target):
                if node_email:
                    node_occurrences.setdefault(node_email, []).append(occ)

    # Deduplicate by msg_id; sort most-recent first
    for email in node_occurrences:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for occ in sorted(
            node_occurrences[email],
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        ):
            mid = occ["msg_id"]
            if mid and mid not in seen:
                seen.add(mid)
                deduped.append(occ)
        node_occurrences[email] = deduped

    elements: list[dict[str, Any]] = []

    for node in graph.get("nodes", []):
        email = node.get("email", "")
        node_degree = degree.get(email, 0)
        size = 30 + int(60 * node_degree / max(max_degree, 1))
        occs = node_occurrences.get(email, [])
        primary_ref = occs[0]["msg_id"] if occs else ""

        elements.append(
            {
                "data": {
                    "id": email,
                    "label": email,
                    "type": node.get("type", "EmailAddress"),
                    "degree": node_degree,
                    "size": size,
                    "primary_ref": primary_ref,
                    "occurrences": occs,
                }
            }
        )

    for edge in graph.get("edges", []):
        source = edge.get("from", "")
        target = edge.get("to", "")
        edge_type = edge.get("type", "")
        edge_id = f"{edge_type}:{source}->{target}"
        elements.append(
            {
                "data": {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "frequency": edge.get("frequency", 0),
                    "source_references": edge.get("source_references", []),
                    "timestamps": edge.get("timestamps", []),
                }
            }
        )
    return elements


def _build_html(elements: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(elements)
    return _GRAPH_HTML_TEMPLATE.replace("__GCLI_TITLE__", title).replace(
        "__GCLI_ELEMENTS__", payload
    )


@command_contract(VISUALIZE_COMMAND_SPEC)
def visualize_command(
    input_artifact: Annotated[
        str | None,
        typer.Option("--input-artifact", help="Upstream graph artifact id or file path"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Output HTML file path"),
    ] = None,
) -> None:
    """Render a graph artifact as a Cytoscape.js HTML visualization."""
    if not input_artifact:
        raise typer.BadParameter("Missing --input-artifact.")
    try:
        payload = load_artifact_reference(input_artifact)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not payload.entries:
        raise typer.BadParameter("Input artifact is empty.")
    graph = payload.entries[0]
    if "nodes" not in graph or "edges" not in graph:
        raise typer.BadParameter("Input artifact does not contain graph data.")

    elements = _to_cytoscape_elements(graph)
    html = _build_html(elements, title="gcli Email Graph")
    output = output or (Path(".artifacts") / f"{build_artifact_id('visualize')}.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    console.print(f"[green]Visualization written:[/green] {output.resolve()}")
