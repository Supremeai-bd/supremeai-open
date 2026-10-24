import * as vscode from 'vscode';
import * as path from 'path';

export class DependencyGraphProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'supremeai.dependencyGraph';

  private _view?: vscode.WebviewView;

  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ) {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      // Note: retainContextWhenHidden is not a standard option in WebviewOptions
      // We'll remove this property as it's causing compilation errors
      localResourceRoots: [this._extensionUri]
    };

    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(data => {
      switch (data.type) {
        case 'dependencyRequest':
          // ডিপেন্ডেন্সি বিশ্লেষণ করা
          this.handleDependencyRequest();
          break;
      }
    });
  }

  private handleDependencyRequest() {
    // ডিপেন্ডেন্সি বিশ্লেষণ লজিক
    if (this._view) {
      // ডিপেন্ডেন্সি ডেটা জেনারেট করা এবং ওয়েবভিউ আপডেট করা
      const dependencies = this.generateDependencyData();
      this._view.webview.postMessage({
        type: 'updateGraph',
        data: dependencies
      });
    }
  }

  private generateDependencyData(): any {
    // ডিপেন্ডেন্সি ডেটা জেনারেট করার লজিক
    // এটি প্রকৃত ডিপেন্ডেন্সি বিশ্লেষণ করবে
    return {
      nodes: [
        { id: 'app.ts', label: 'app.ts' },
        { id: 'service.ts', label: 'service.ts' },
        { id: 'utils.ts', label: 'utils.ts' },
        { id: 'types.ts', label: 'types.ts' }
      ],
      links: [
        { source: 'app.ts', target: 'service.ts' },
        { source: 'app.ts', target: 'types.ts' },
        { source: 'service.ts', target: 'utils.ts' },
        { source: 'service.ts', target: 'types.ts' }
      ]
    };
  }

  private _getHtmlForWebview(webview: vscode.Webview) {
    // Correct way to reference local files for webview
    // We no longer try to load an external CSS file
    // Instead we use CSS variables for VSCode theming

    // ডিপেন্ডেন্সি গ্রাফ HTML তৈরি
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https: vscode-webview-resource:; script-src 'unsafe-inline' 'unsafe-eval' https: vscode-webview-resource:; img-src 'self' data: https: vscode-webview-resource:;">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dependency Graph</title>
        <!-- Removed external stylesheet reference -->
        <style>
          body {
            margin: 0;
            padding: 10px;
            overflow: hidden;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
          }
          #graph-container {
            width: 100%;
            height: calc(100vh - 40px);
          }
          .node {
            stroke: #fff;
            stroke-width: 1.5px;
          }
          .link {
            stroke: #999;
            stroke-opacity: 0.6;
          }
          .node-label {
            font-size: 12px;
            pointer-events: none;
          }
          .controls {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 10;
          }
          button {
            background-color: #404040;
            color: white;
            border: none;
            padding: 5px 10px;
            margin-left: 5px;
            cursor: pointer;
            border-radius: 3px;
          }
          button:hover {
            background-color: #505050;
          }
        </style>
      </head>
      <body>
        <div class="controls">
          <button id="refresh-btn">Refresh</button>
          <button id="zoom-in">Zoom In</button>
          <button id="zoom-out">Zoom Out</button>
        </div>
        <div id="graph-container"></div>

        <!-- D3.js CDN (offline হলে local d3 ফাংশন fallback) -->
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script>
          // CDN ব্যর্থ হলে fallback stub
          if (typeof d3 === 'undefined') {
            window.d3 = {
              select: () => ({ append: () => ({ attr: () => ({ call: () => {}, append: () => ({ selectAll: () => ({ data: () => ({ enter: () => ({ append: () => ({ attr: () => ({ call: () => {} }) }) }) }) }) }) }) }),
              zoom: () => ({ scaleExtent: () => ({ on: () => ({}) }) }),
              forceSimulation: () => ({ force: () => ({ on: () => ({ restart: () => {} }) }), nodes: () => ({}), alphaTarget: () => ({}), alpha: () => ({ restart: () => {} }) }),
              forceLink: () => ({ id: () => ({ distance: () => ({}) }) }),
              forceManyBody: () => ({ strength: () => ({}) }),
              forceCenter: () => ({}),
              drag: () => ({ on: () => ({}) })
            };
          }
        </script>
        <script>
          // D3.js ব্যবহার করে ডিপেন্ডেন্সি গ্রাফ তৈরি
          const container = d3.select("#graph-container");
          let svg = container.append("svg")
            .attr("width", "100%")
            .attr("height", "100%");
          let g = svg.append("g");

          // Zoom functionality
          const zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on("zoom", (event) => {
              g.attr("transform", event.transform);
            });
          svg.call(zoom);

          // Initialize simulation
          let simulation = d3.forceSimulation()
            .force("link", d3.forceLink().id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(window.innerWidth / 2, window.innerHeight / 2));

          // Button event listeners
          document.getElementById('refresh-btn').addEventListener('click', () => {
            vscode.postMessage({ type: 'dependencyRequest' });
          });

          document.getElementById('zoom-in').addEventListener('click', () => {
            svg.transition().call(zoom.scaleBy, 1.2);
          });

          document.getElementById('zoom-out').addEventListener('click', () => {
            svg.transition().call(zoom.scaleBy, 0.8);
          });

          // ডেটা আপডেট হবে এক্সটেনশন থেকে
          window.addEventListener('message', event => {
            const message = event.data;
            if (message.type === 'updateGraph') {
              updateGraph(message.data);
            }
          });

          function updateGraph(data) {
            // Clear previous graph
            g.selectAll("*").remove();

            // Create links
            const link = g.append("g")
              .attr("class", "links")
              .selectAll("line")
              .data(data.links)
              .enter()
              .append("line")
              .attr("class", "link")
              .attr("stroke-width", 2);

            // Create nodes
            const node = g.append("g")
              .attr("class", "nodes")
              .selectAll("circle")
              .data(data.nodes)
              .enter()
              .append("circle")
              .attr("class", "node")
              .attr("r", 10)
              .call(drag(simulation));

            // Add labels to nodes
            const nodeLabel = g.append("g")
              .attr("class", "node-labels")
              .selectAll("text")
              .data(data.nodes)
              .enter()
              .append("text")
              .attr("class", "node-label")
              .text(d => d.label)
              .attr("dx", 12)
              .attr("dy", 4);

            // Update simulation
            simulation.nodes(data.nodes);
            simulation.force("link").links(data.links);

            // Update positions on each tick
            simulation.on("tick", () => {
              link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

              node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);

              nodeLabel
                .attr("x", d => d.x)
                .attr("y", d => d.y);
            });

            // Restart simulation
            simulation.alpha(0.3).restart();
          }

          // Drag functions
          function drag(simulation) {
            function dragstarted(event, d) {
              if (!event.active) simulation.alphaTarget(0.3).restart();
              d.fx = d.x;
              d.fy = d.y;
            }

            function dragged(event, d) {
              d.fx = event.x;
              d.fy = event.y;
            }

            function dragended(event, d) {
              if (!event.active) simulation.alphaTarget(0);
              d.fx = null;
              d.fy = null;
            }

            return d3.drag()
              .on("start", dragstarted)
              .on("drag", dragged)
              .on("end", dragended);
          }

          // Initial request for data
          vscode.postMessage({ type: 'dependencyRequest' });
        </script>
      </body>
      </html>
    `;
  }
}



