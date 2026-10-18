// Read aloud (speech synthesis) and voice input (speech recognition) using the browser's own engines.
const VOICE_LANG: Record<string, string> = { en: "en-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN", kn: "kn-IN", mr: "mr-IN" };

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function speak(text: string, language = "en", rate = 1): void {
  if (!canSpeak()) return;
  window.speechSynthesis.cancel();
  const clean = text.replace(/[*_#>`|]/g, "").replace(/₹/g, "rupees ");
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.lang = VOICE_LANG[language] ?? "en-IN";
  utterance.rate = rate;
  window.speechSynthesis.speak(utterance);
}


export function canListen(): boolean {
  return typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
}

export function listen(language: string, onText: (text: string) => void, onEnd: () => void): () => void {
  const Recognition = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
  const recognition = new Recognition();
  recognition.lang = VOICE_LANG[language] ?? "en-IN";
  recognition.interimResults = false;
  recognition.onresult = (event: any) => onText(event.results[0][0].transcript);
  recognition.onend = onEnd;
  recognition.onerror = onEnd;
  recognition.start();
  return () => recognition.stop();
}
