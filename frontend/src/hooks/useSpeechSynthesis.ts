import { useCallback, useEffect, useState } from 'react'

/** Browser-native text-to-speech (Web Speech API) - free, no backend, no
 * API key. Supported in every major browser (unlike SpeechRecognition,
 * which is Chrome/Edge-only), so no feature-detection gate is needed. */
export function useSpeechSynthesis() {
  const [speaking, setSpeaking] = useState(false)

  useEffect(() => () => window.speechSynthesis?.cancel(), [])

  const speak = useCallback((text: string) => {
    if (!window.speechSynthesis || !text.trim()) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utterance)
  }, [])

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }, [])

  return { speaking, speak, stop }
}
