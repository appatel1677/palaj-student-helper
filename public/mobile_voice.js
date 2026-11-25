(function () {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  let recognition = null;
  let isListening = false;

  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function injectMobileMicButton() {
    if (document.getElementById("palaj-guj-mic-btn")) return;

    const btn = document.createElement("button");
    btn.id = "palaj-guj-mic-btn";
    btn.type = "button";
    btn.title = "ગુજરાતીમાં બોલવા માટે દબાવો";
    btn.innerHTML = "🎤 ગુજરાતી માઈક";
    Object.assign(btn.style, {
      position: "fixed",
      bottom: "88px",
      right: "18px",
      zIndex: "99999",
      background: "#2563EB",
      color: "#FFFFFF",
      border: "none",
      borderRadius: "999px",
      padding: "10px 16px",
      fontSize: "14px",
      fontWeight: "bold",
      boxShadow: "0 4px 12px rgba(0,0,0,0.28)",
      cursor: "pointer"
    });

    btn.addEventListener("click", function () {
      if (isListening && recognition) {
        recognition.stop();
        return;
      }

      recognition = new SpeechRecognition();
      recognition.lang = "gu-IN";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = function () {
        isListening = true;
        btn.innerHTML = "🔴 સાંભળું છું... (બોલો)";
        btn.style.background = "#DC2626";
      };

      recognition.onresult = function (event) {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        const textarea = document.querySelector("textarea");
        if (textarea && transcript.trim()) {
          setNativeValue(textarea, transcript.trim());
        }
        if (event.results[event.results.length - 1].isFinal && transcript.trim()) {
          setTimeout(() => {
            const sendBtn =
              document.querySelector('button[type="submit"]') ||
              document.querySelector('button[aria-label*="Send" i]') ||
              document.querySelector('button[aria-label*="Submit" i]');
            if (sendBtn && !sendBtn.disabled) {
              sendBtn.click();
            } else if (textarea) {
              textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
            }
          }, 250);
        }
      };

      recognition.onerror = function () {
        isListening = false;
        btn.innerHTML = "🎤 ગુજરાતી માઈક";
        btn.style.background = "#2563EB";
      };

      recognition.onend = function () {
        isListening = false;
        btn.innerHTML = "🎤 ગુજરાતી માઈક";
        btn.style.background = "#2563EB";
      };

      try {
        recognition.start();
      } catch (e) {
        isListening = false;
      }
    });

    document.body.appendChild(btn);
  }

  setInterval(injectMobileMicButton, 1200);
})();
