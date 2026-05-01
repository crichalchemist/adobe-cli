# cli-anything-premierepro — SOP & Architecture

Standard Operating Procedure for developers and agents working with this harness.

---

## Architecture

Two-layer IPC stack:

```
Python CLI
  → HTTP POST localhost:7788 (requests)
    → CEP panel (Chromium/Node.js via CEPHtmlEngine)
      → csInterface.evalScript()
        → Premiere Pro ExtendScript (ESTK / ES3)
          → string result back up the chain
```

- The CEP panel runs in a separate OS process (`CEPHtmlEngine`) launched by Premiere Pro on startup.
- ExtendScript results are always returned as strings. Structured data must be `JSON.stringify`'d in the ESTK script and parsed by `eval_json()` in Python.
- The Python side is a Click CLI (`premierepro_cli.py`) that speaks to the bridge over plain HTTP.

---

## CEP Extension Setup

These are non-obvious. Each item below cost real debug time.

### 1. CSXS Version

PPro 2025 (version 25.x) uses **CSXS 12**. The manifest must declare:

```xml
<ExtensionManifest Version="8.0" ...>
  ...
  <RequiredRuntime Name="CSXS" Version="12.0"/>
```

Using `Version="7.0"` or `Version="11.0"` causes **silent rejection** — the Extensions menu stays greyed out, no error surfaced anywhere.

### 2. CEF Command Line Flags

All four flags are required in the manifest `<CEFCommandLine>` block:

```xml
<CEFCommandLine>
  <Parameter>--allow-file-access</Parameter>
  <Parameter>--allow-file-access-from-files</Parameter>
  <Parameter>--enable-nodejs</Parameter>
  <Parameter>--mixed-context</Parameter>
</CEFCommandLine>
```

- Without `--enable-nodejs`: CEPHtmlEngine never starts; JS is never executed.
- Without `--mixed-context`: `csInterface` and Node.js `require()` cannot share the same V8 context.

### 3. AutoVisible Must Be true

```xml
<AutoVisible>true</AutoVisible>
```

`false` means JS never executes until the panel is manually opened. Since the panel starts hidden and the Extensions menu is greyed before any extension loads, this creates an unresolvable chicken-and-egg. Always set `true`.

### 4. Panel Must Have Visible Size

1×1 px panels are deferred by Chromium. Minimum working size is approximately 200×30 px.

```xml
<Geometry>
  <Size><Height>30</Height><Width>200</Width></Size>
</Geometry>
```

### 5. CSInterface.js Must Be Explicitly Loaded

It is **not** auto-injected. Copy it from the PPro app bundle:

```
{PPro app bundle}/Contents/CEP/extensions/com.adobe.URLAnchorExtract.extension/js/CSInterface.js
```

Load it in `index.html` **before** `main.js`:

```html
<script src="js/CSInterface.js"></script>
<script src="js/main.js"></script>
```

### 6. PlayerDebugMode for Both CSXS Versions

Required to allow unsigned extensions:

```bash
defaults write com.adobe.CSXS.11 PlayerDebugMode 1
defaults write com.adobe.CSXS.12 PlayerDebugMode 1
```

### 7. No `<ScriptPath>` in Manifest

Do **not** include a `<ScriptPath>` element pointing to `main.js`. `ScriptPath` is for ExtendScript files that run in PPro's ESTK engine. `main.js` is a Node.js file running in CEPHtmlEngine — it is loaded via `<MainPath>./index.html</MainPath>` and the `<script>` tag in `index.html`. Mixing the two causes `main.js` to be evaluated twice in wrong contexts.

### 8. Extension Install via Symlink

```bash
ln -s /path/to/cep \
  ~/Library/Application\ Support/Adobe/CEP/extensions/com.your.bundle.id
```

The symlink target is the directory containing `CSXS/manifest.xml`.

### 9. Proof-of-Life Diagnostic

At the top of `main.js`, before any `require()`:

```js
try {
  require('fs').writeFileSync('/tmp/cep-alive.txt', new Date().toISOString());
} catch(e) {}
```

If `/tmp/cep-alive.txt` does not exist after restarting PPro → JS never ran → check items 1–7 above.

---

## ExtendScript API Notes (PPro 2025 ESTK Quirks)

### No JSON

ESTK runs ES3. `typeof JSON === "undefined"` is true. The bridge prepends a JSON polyfill to every `evalScript` call. Do not assume `JSON` is available if writing new ESTK scripts that run outside the bridge.

### createMarker Takes Seconds (Float), Not a Time Object

```js
// correct
clip.createMarker(30.5);

// throws "Illegal Parameter type"
clip.createMarker(new Time());
```

### setPlayerPosition Takes Ticks

Construct a `Time` object, assign its `.seconds` property, then pass `.ticks` as the argument — passing `.seconds` directly as an argument is wrong:

```js
var tc = new Time();
tc.seconds = 30.5;
sequence.setPlayerPosition(tc.ticks);     // correct

sequence.setPlayerPosition(tc.seconds);   // wrong — argument must be ticks
```

### No Array.forEach, No Object.keys

ES3 — use `for` loops.

### Always Wrap in an IIFE

Scripts evaluated via `evalScript` share the ESTK global scope across calls. Wrap every script in an immediately-invoked function expression to avoid variable collisions:

```js
(function() {
    var seq = app.project.activeSequence;
    // ...
    return JSON.stringify(result);
})()
```

### IPC Roundtrip Is Async

Each `evalScript` call is async. Results come back as strings. All structured data must be `JSON.stringify`'d in the script side and parsed by `eval_json()` in Python.

---

## IPC Protocol

Base URL: `http://localhost:7788`

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/ping` | — | `{"ok":true,"version":"1.0.0","app":"premierepro"}` |
| POST | `/eval` | `{"script":"<ExtendScript>"}` | `{"ok":true,"result":"<string>"}` or `{"ok":false,"error":"ExtendScript error","raw":"EvalScript error."}` |
| POST | `/scrub` | `{"seconds":1.5}` | `{"ok":true}` |

---

## Known Limitations

- **One open project at a time** — Premiere Pro constraint.
- **CEP panel must be running** — loaded automatically on PPro launch once the manifest is correct. On the very first install, PPro must be restarted after the symlink is created.
- **`activeSequence` can be null** — callers must handle this or set it first via `set_active_sequence()`.
- **AME export** (`app.encoder.encodeSequence`) requires Adobe Media Encoder to be installed separately.
- **ExtendScript runs synchronously in PPro's UI thread** — avoid long-running scripts; they block the application.

---

## .prproj Format Notes

`.prproj` files are gzip-compressed XML. Parse offline (no PPro required):

```python
import gzip
import xml.etree.ElementTree as ET

with gzip.open("project.prproj", "rb") as f:
    tree = ET.parse(f)
```

- **Sequences**: `<Sequence>` elements; deduplicate by `ObjectUID` attribute.
- **Media files**: under `<ProjectItem>` children; the `Name` child element may be absent — fall back to the `Path` attribute.
- The offline parser in `utils/prproj_parser.py` handles these cases.

---

## Debug Port

A `.debug` file in the extension root enables Chrome DevTools on port 7778:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Extension Id="com.cli-anything.premierepro.panel">
  <HostList>
    <Host Name="PPRO" Port="7778"/>
  </HostList>
</Extension>
```

Connect via:

```
chrome://inspect → Configure → add localhost:7778
```
