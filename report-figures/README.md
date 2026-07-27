# Code Analyzer — Report Figures

PNG diagrams for the BCA project report, generated from the actual project
(FastAPI + Next.js, algorithms: McCabe Cyclomatic Complexity, Winnowing,
Halstead + Maintainability Index).

Each PNG is light-themed for clean printing on white paper. Insert the matching
file next to its caption in the report.

| File | Report caption |
|------|----------------|
| `fig-1-1-agile.png` | Figure 1.1: Agile Development Method of Code Analyzer |
| `fig-3-1-usecase.png` | Figure 3.1: Use Case Diagram of Code Analyzer |
| `fig-3-2-gantt.png` | Figure 3.2: Gantt Chart of Code Analyzer |
| `fig-3-3-class.png` | Figure 3.3: Class Diagram of Code Analyzer |
| `fig-3-4-object.png` | Figure 3.4: Object Diagram of Code Analyzer |
| `fig-3-5-state.png` | Figure 3.5: State Diagram of Code Analyzer |
| `fig-3-6-sequence.png` | Figure 3.6: Sequence Diagram of Code Analyzer |
| `fig-3-7-activity.png` | Figure 3.7: Activity Diagram of Code Analyzer |
| `fig-3-8-refined-class.png` | Figure 3.8: Refined Class Diagram of Code Analyzer |
| `fig-3-9-refined-object.png` | Figure 3.9: Refined Object Diagram of Code Analyzer |
| `fig-3-10-component.png` | Figure 3.10: Component Diagram of Code Analyzer |
| `fig-3-11-deployment.png` | Figure 3.11: Deployment Diagram of Code Analyzer |
| `fig-3-12-winnowing.png` | Figure 3.12: The architecture of the Winnowing Algorithm |

## Regenerating

Most sources are in `src/*.mmd` (Mermaid). To re-render one after editing:

```bash
cd report-figures
npx -y @mermaid-js/mermaid-cli@11 -i src/<name>.mmd -o <name>.png \
  -c mermaid-config.json -p puppeteer-config.json -b white -s 3
```

The use-case diagram is hand-drawn UML (line stick-figure actors), so its
source is `src/fig-3-1-usecase.svg`. Re-render it with headless Chrome:

```bash
cd report-figures
CHROME="$HOME/.cache/puppeteer/chrome-headless-shell/mac_arm-148.0.7778.97/chrome-headless-shell-mac-arm64/chrome-headless-shell"
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --force-device-scale-factor=3 --window-size=1000,1320 \
  --default-background-color=FFFFFFFF \
  --screenshot="fig-3-1-usecase.png" "file://$PWD/src/fig-3-1-usecase.svg"
```

- `mermaid-config.json` — the light theme (light-indigo fills, dark text).
- `puppeteer-config.json` — points at the local headless Chrome used for rendering.
