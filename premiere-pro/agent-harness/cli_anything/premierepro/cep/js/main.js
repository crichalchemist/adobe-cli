/* cli-anything-premierepro CEP bridge
 * HTTP server on localhost:7788.
 * POST /eval — run ExtendScript in Premiere Pro context, return JSON result
 * POST /scrub — move active sequence playhead to a timecode
 * GET  /ping  — health check
 */

// Diagnostic: write proof-of-life file so we know if JS executed at all
try { require('fs').writeFileSync('/tmp/cep-alive.txt', new Date().toISOString()); } catch(e) {}

var csInterface = new CSInterface();
var http = require('http');

var PORT = parseInt(process.env.CLI_ANYTHING_PORT || '7788', 10);

// ExtendScript (ESTK) is ES3 — no native JSON. Prepend a polyfill to every evalScript call.
var JSON_POLYFILL = 'if(typeof JSON==="undefined"){var JSON={};' +
    'JSON.stringify=function(v,r,s){' +
    '  if(v===null||v===undefined)return "null";' +
    '  if(typeof v==="number")return isFinite(v)?String(v):"null";' +
    '  if(typeof v==="boolean")return String(v);' +
    '  if(typeof v==="string"){' +
    '    return \'"\'+v.replace(/\\\\/g,"\\\\\\\\").replace(/"/g,\'\\\\"\')' +
    '      .replace(/\\n/g,"\\\\n").replace(/\\r/g,"\\\\r").replace(/\\t/g,"\\\\t")+\'"\';' +
    '  }' +
    '  if(v instanceof Array){' +
    '    var a=[];for(var i=0;i<v.length;i++)a.push(JSON.stringify(v[i]));' +
    '    return "["+a.join(",")+"]";' +
    '  }' +
    '  if(typeof v==="object"){' +
    '    var b=[];for(var k in v){if(Object.prototype.hasOwnProperty.call(v,k))' +
    '      b.push(JSON.stringify(k)+":"+JSON.stringify(v[k]));}' +
    '    return "{"+b.join(",")+"}";' +
    '  }' +
    '  return undefined;' +
    '};' +
    'JSON.parse=function(s){return eval("("+s+")");}' +
    '};';

function handleRequest(req, res) {
    if (req.method === 'GET' && req.url === '/ping') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, version: '1.0.0', app: 'premierepro' }));
        return;
    }

    if (req.method === 'POST' && req.url === '/eval') {
        var body = '';
        var bodySize = 0;
        req.on('data', function(chunk) {
            bodySize += chunk.length;
            if (bodySize > 10 * 1024 * 1024) { req.destroy(); return; }
            body += chunk.toString();
        });
        req.on('end', function() {
            var payload;
            try {
                payload = JSON.parse(body);
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: false, error: 'Invalid JSON: ' + e.message }));
                return;
            }
            var script = JSON_POLYFILL + (payload.script || '');
            csInterface.evalScript(script, function(result) {
                if (result === 'EvalScript error.' || result === null || result === undefined) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: false, error: 'ExtendScript error', raw: result }));
                } else {
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: true, result: result }));
                }
            });
        });
        return;
    }

    if (req.method === 'POST' && req.url === '/scrub') {
        var body = '';
        var bodySize = 0;
        req.on('data', function(chunk) {
            bodySize += chunk.length;
            if (bodySize > 10 * 1024 * 1024) { req.destroy(); return; }
            body += chunk.toString();
        });
        req.on('end', function() {
            var payload;
            try {
                payload = JSON.parse(body);
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: false, error: 'Invalid JSON: ' + e.message }));
                return;
            }
            var seconds = parseFloat(payload.seconds) || 0;
            var script = '(function(){' +
                'var seq = app.project.activeSequence;' +
                'if (!seq) return JSON.stringify({error:"No active sequence"});' +
                'var tc = new Time();' +
                'tc.seconds = ' + seconds + ';' +
                'seq.setPlayerPosition(tc.ticks);' +
                'return JSON.stringify({ok:true,seconds:' + seconds + '});' +
                '})()';
            csInterface.evalScript(script, function(result) {
                var data;
                try { data = JSON.parse(result); } catch(e) { data = { ok: false, error: result }; }
                var status = (data && data.ok === false) ? 500 : 200;
                res.writeHead(status, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(data));
            });
        });
        return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: 'Not found: ' + req.url }));
}

var server = http.createServer(handleRequest);
server.listen(PORT, '127.0.0.1', function() {
    console.log('cli-anything-premierepro: HTTP bridge listening on port ' + PORT);
});

server.on('error', function(err) {
    if (err.code === 'EADDRINUSE') {
        console.error('cli-anything-premierepro: Port ' + PORT + ' already in use.');
    } else {
        console.error('cli-anything-premierepro server error:', err);
    }
});
