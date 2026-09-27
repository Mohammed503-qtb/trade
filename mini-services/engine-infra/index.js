// engine-infra — غلاف supervisor المحلي (build_plan A.2، قرار D-15)
//
// يشغّل `infra/local/supervisor.py run` (الوضع الأمامي) من venv المحرك.
// المنصة تشغّل هذا الملف عبر bun وتضمن بقاءه؛ supervisor بدوره يدير
// postgres → nats → seaweedfs → migrate → worker بإقلاع متدرج وصحة حقيقية.
//
// حلقة إعادة المحاولة: لو خرج supervisor (قفل مشغول مثلًا) نعيد بعد مهلة —
// القفل داخل supervisor يمنع التزامن الفعلي، والقفز هنا يلتقط الخلافة.

import { spawn } from 'node:child_process'

const ENGINE_DIR = '/home/z/my-project/engine'
const PYTHON = `${ENGINE_DIR}/.venv/bin/python`
const RETRY_S = 5

let child = null
let shuttingDown = false

function log(msg) {
  console.log(`[engine-infra] ${new Date().toISOString()} ${msg}`)
}

function startSupervisor() {
  if (shuttingDown) return
  log('starting supervisor (run mode)')
  child = spawn(PYTHON, ['infra/local/supervisor.py', 'run'], {
    cwd: ENGINE_DIR,
    stdio: ['ignore', 'inherit', 'inherit'],
    env: { ...process.env },
  })

  child.on('exit', (code, signal) => {
    if (shuttingDown) return
    log(`supervisor exited (code=${code} signal=${signal}) — retry in ${RETRY_S}s`)
    setTimeout(startSupervisor, RETRY_S * 1000)
  })
}

process.on('SIGTERM', () => {
  shuttingDown = true
  log('SIGTERM — stopping supervisor (graceful reverse-order shutdown)')
  if (child) child.kill('SIGTERM')
})
process.on('SIGINT', () => {
  shuttingDown = true
  log('SIGINT — stopping supervisor (graceful reverse-order shutdown)')
  if (child) child.kill('SIGTERM')
})

// إبقاء عملية bun حية ما دام الابن حيًا
child ?? null
startSupervisor()
