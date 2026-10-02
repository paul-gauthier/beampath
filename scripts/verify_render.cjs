// Compatibility entrypoint for fresh PNG/SVG pixel comparison.
const fs = require('fs');
const path = require('path');
const {spawnSync} = require('child_process');
const root = path.resolve(__dirname, '..');
const localPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.PYTHON || (fs.existsSync(localPython) ? localPython : 'python3');
const result = spawnSync(python, [path.join(__dirname, 'verify_schematic.py'), '--png', ...process.argv.slice(2)],
                         {cwd: root, stdio: 'inherit'});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
