// 录音 + 音量包络分析：用于估算语速与停顿（不依赖任何模型）。
export async function startAudioCapture() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const AudioCtx = window.AudioContext || window.webkitAudioContext
  const ctx = new AudioCtx()
  const source = ctx.createMediaStreamSource(stream)
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 1024
  source.connect(analyser)
  const buffer = new Uint8Array(analyser.fftSize)

  const startedAt = performance.now()
  let lastAt = startedAt
  let speechTime = 0
  let inSpeech = false
  let silenceStart = null
  let hadSpeech = false
  const pauses = []

  const timer = setInterval(() => {
    analyser.getByteTimeDomainData(buffer)
    let sum = 0
    for (let i = 0; i < buffer.length; i += 1) {
      const v = (buffer[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / buffer.length)
    const now = performance.now()
    const dt = (now - lastAt) / 1000
    lastAt = now

    if (rms > 0.02) {
      if (!inSpeech) {
        inSpeech = true
        if (hadSpeech && silenceStart !== null) {
          const gap = (now - silenceStart) / 1000
          if (gap >= 0.15) pauses.push(gap)
        }
        hadSpeech = true
        silenceStart = null
      }
      speechTime += dt
    } else if (inSpeech) {
      inSpeech = false
      silenceStart = now
    }
  }, 50)

  return {
    stop() {
      clearInterval(timer)
      const duration = (performance.now() - startedAt) / 1000
      stream.getTracks().forEach((t) => t.stop())
      if (ctx.state !== 'closed') ctx.close()
      return {
        duration_sec: Number(duration.toFixed(2)),
        speech_time_sec: Number(speechTime.toFixed(2)),
        pauses: pauses.map((p) => Number(p.toFixed(2))),
      }
    },
  }
}
