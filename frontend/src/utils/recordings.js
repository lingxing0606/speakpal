// 录音回放：每句录音只存在本浏览器的 IndexedDB 里，不上传服务器。
// 键 = 会话 id + 第几句用户发言（与后端 turn_index 一致，从 1 开始）。
// 记录里带用户名，换账号登录时不会读到别人的录音；主动退出 / 清空数据时整库清掉。

const DB_NAME = 'speakpal-recordings'
const STORE = 'clips'
// 只留最近这么多次练习的录音，免得浏览器存储越攒越大
const KEEP_SESSIONS = 30

let dbPromise = null

function openDb() {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('indexedDB unavailable'))
      return
    }
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      const store = req.result.createObjectStore(STORE, { keyPath: 'key' })
      store.createIndex('sessionId', 'sessionId')
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  }).catch((e) => {
    dbPromise = null
    throw e
  })
  return dbPromise
}

function done(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem('sp_user') || 'null')?.username || ''
  } catch {
    return ''
  }
}

/** 存一句录音。失败（隐私模式、存储满）静默忽略：回放只是锦上添花，不能影响练习。 */
export async function saveRecording(sessionId, turnIndex, blob) {
  if (!sessionId || !turnIndex || !blob || !blob.size) return
  try {
    const db = await openDb()
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put({
      key: `${sessionId}:${turnIndex}`,
      sessionId: Number(sessionId),
      turnIndex: Number(turnIndex),
      user: currentUser(),
      blob,
      createdAt: Date.now(),
    })
    await done(tx)
    await prune()
  } catch {
    // 忽略
  }
}

/** 取某次练习的全部录音：{ [turnIndex]: Blob } */
export async function loadRecordings(sessionId) {
  const out = {}
  if (!sessionId) return out
  try {
    const db = await openDb()
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).index('sessionId').getAll(Number(sessionId))
    const rows = await new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result || [])
      req.onerror = () => reject(req.error)
    })
    const user = currentUser()
    for (const row of rows) {
      if (row.user && user && row.user !== user) continue
      out[row.turnIndex] = row.blob
    }
  } catch {
    // 忽略
  }
  return out
}

async function prune() {
  const db = await openDb()
  const tx = db.transaction(STORE, 'readwrite')
  const store = tx.objectStore(STORE)
  const req = store.getAll()
  req.onsuccess = () => {
    const rows = req.result || []
    const latest = new Map()
    for (const row of rows) {
      latest.set(row.sessionId, Math.max(latest.get(row.sessionId) || 0, row.createdAt || 0))
    }
    const keep = new Set(
      [...latest.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, KEEP_SESSIONS)
        .map(([id]) => id)
    )
    for (const row of rows) {
      if (!keep.has(row.sessionId)) store.delete(row.key)
    }
  }
  await done(tx)
}

/** 清空本浏览器里的所有录音（主动退出、清空数据、注销时调用） */
export async function clearRecordings() {
  try {
    const db = await openDb()
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).clear()
    await done(tx)
  } catch {
    // 忽略
  }
}

// ---------------------------------------------------------------- 播放
let player = null
let playerUrl = ''

export function stopRecording() {
  if (player) {
    player.pause()
    player = null
  }
  if (playerUrl) {
    URL.revokeObjectURL(playerUrl)
    playerUrl = ''
  }
}

/** 播放一句录音；同一时间只放一句。返回 false 表示放不出来。 */
export async function playRecording(blob, onEnd) {
  stopRecording()
  if (!blob) return false
  playerUrl = URL.createObjectURL(blob)
  const audio = new Audio(playerUrl)
  player = audio
  audio.onended = () => {
    if (player === audio) stopRecording()
    onEnd && onEnd()
  }
  try {
    await audio.play()
    return true
  } catch {
    if (player === audio) stopRecording()
    onEnd && onEnd()
    return false
  }
}
