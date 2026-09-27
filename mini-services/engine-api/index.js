// engine-api — غلاف uvicorn لـ FastAPI (build_plan A.3، قرار ADR-007)
//
// يعمل بغلافه المستقل عن supervisor عمدًا: إعادة تشغيل البنية التحتية
// لا تُسقط الواجهة، وإعادة تشغيل الواجهة لا تُسقط البيانات.
// uvicorn من venv المحرك — التطبيق engine_api.main:app على 127.0.0.1:4001
// (الوصول الخارجي عبر بوابة المنصة: ?XTransformPort=4001).

import { spawn } from 'node:child_process'

const ENGINE_DIR = '/home/z/my-project/engine'
const PYTHON = `${ENGINE_DIR}/.venv/bin/python`
const HOST = '127.0.0.1'
const PORT = 4001
const RETRY_S = 5

let child = null
let shuttingDown = false

function log(msg) {
  console.log(`[engine-api] ${new Date().toISOString()} ${msg}`)
}

function startApi() {
  if (shuttingDown) return
  log(`starting uvicorn on ${HOST}:${PORT}`)
  child = spawn(
    PYTHON,
    [
      '-m', 'uvicorn',
      'engine_api.main:app',
      '--host', HOST,
      '--port', String(PORT),
    ],
    {
      cwd: ENGINE_DIR,
      stdio: ['ignore', 'inherit', 'inherit'],
      env: { ...process.env },
    }
  )

  child.on('exit', (code, signal) => {
    if (shuttingDown) return
    log(`uvicorn exited (code=${code} signal=${signal}) — retry in ${RETRY_S}s`)
    setTimeout(startApi, RETRY_S * 1000)
  })
}

process.on('SIGTERM', () => {
  shuttingDown = true
  log('SIGTERM — stopping uvicorn')
  if (child) child.kill('SIGTERM')
})
process.on('SIGINT', () => {
  shuttingDown = true
  log('SIGINT — stopping uvicorn')
  if (child) child.kill('SIGTERM')
})

startApi()
