export function speak(text, lang = 'en-US') {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = lang
  utter.rate = 0.95
  window.speechSynthesis.speak(utter)
}

export function createRecognizer(onResult, onEnd, onError) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) return null

  const rec = new SpeechRecognition()
  rec.lang = 'en-US'
  rec.interimResults = true
  rec.continuous = false
  rec.onresult = (event) => {
    let text = ''
    for (let i = 0; i < event.results.length; i += 1) {
      text += event.results[i][0].transcript
    }
    onResult(text)
  }
  rec.onend = () => onEnd()
  rec.onerror = (event) => onError && onError(event)
  return rec
}
