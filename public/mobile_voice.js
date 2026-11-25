(function () {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;

  function setReactTextareaValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function createHiddenCameraInput() {
    let camInput = document.getElementById("palaj-camera-input");
    if (camInput) return camInput;

    camInput = document.createElement("input");
    camInput.id = "palaj-camera-input";
    camInput.type = "file";
    camInput.accept = "image/*";
    camInput.setAttribute("capture", "environment");
    camInput.style.display = "none";

    camInput.addEventListener("change", function () {
      if (!camInput.files || !camInput.files.length) return;
      const file = camInput.files[0];

      // Chainlit ના અસલી hidden file input માં ફોટો મોકલો જેથી ચેટ બોક્સમાં અટેચ થઈ જાય
      const chainlitFileInput = Array.from(document.querySelectorAll('input[type="file"]'))
        .find((inp) => inp.id !== "palaj-camera-input");

      if (chainlitFileInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        chainlitFileInput.files = dt.files;
        chainlitFileInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
      camInput.value = "";
    });

    document.body.appendChild(camInput);
    return camInput;
  }

  function injectInlineComposerIcons() {
    // જૂનું તરેતું બટન હોય તો હટાવી દો
    const oldFloat = document.getElementById("palaj-guj-mic-btn");
    if (oldFloat) oldFloat.remove();

    if (document.getElementById("palaj-inline-tools")) return;

    const textarea = document.querySelector("textarea");
    if (!textarea) return;

    // ચેટ બોક્સની નીચેની ટૂલબાર શોધો (જ્યાં Attach 📎 અને Settings ⚙️ બટન છે)
    const composerBox = textarea.closest("form") || textarea.parentElement?.parentElement;
    if (!composerBox) return;

    const existingBtns = composerBox.querySelectorAll("button");
    if (!existingBtns.length) return;
    const anchorBtn = existingBtns[0];
    const toolbarRow = anchorBtn.parentElement;
    if (!toolbarRow) return;

    const wrapper = document.createElement("span");
    wrapper.id = "palaj-inline-tools";
    wrapper.style.display = "inline-flex";
    wrapper.style.alignItems = "center";
    wrapper.style.gap = "4px";
    wrapper.style.marginLeft = "2px";

    // ૧. કેમેરા આઈકોન (Chainlit ની અસલી સ્ટાઈલમાં)
    const camBtn = document.createElement("button");
    camBtn.type = "button";
    camBtn.title = "કેમેરાથી ફોટો પાડો";
    camBtn.setAttribute("aria-label", "કેમેરાથી ફોટો પાડો");
    camBtn.innerHTML = `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>`;
    Object.assign(camBtn.style, {
      background: "transparent",
      border: "none",
      color: "inherit",
      opacity: "0.85",
      padding: "6px",
      borderRadius: "9999px",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    });
    camBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const inp = createHiddenCameraInput();
      inp.click();
    });

    // ૨. માઈક આઈકોન (Chainlit ની અસલી સ્ટાઈલમાં — બોલવાથી ગુજરાતીમાં લખાશે, પછી તમે Send દબાવો)
    const micBtn = document.createElement("button");
    micBtn.id = "palaj-inline-mic-btn";
    micBtn.type = "button";
    micBtn.title = "બોલીને ગુજરાતીમાં લખો";
    micBtn.setAttribute("aria-label", "બોલીને ગુજરાતીમાં લખો");
    const micSvg = `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>`;
    micBtn.innerHTML = micSvg;
    Object.assign(micBtn.style, {
      background: "transparent",
      border: "none",
      color: "inherit",
      opacity: "0.85",
      padding: "6px",
      borderRadius: "9999px",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "all 0.2s ease"
    });

    micBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      if (!SpeechRecognition) {
        alert("આ બ્રાઉઝરમાં વોઈસ ટાઈપિંગ સપોર્ટ નથી — કૃપા કરીને Google Chrome વાપરો.");
        return;
      }

      if (isListening && recognition) {
        recognition.stop();
        return;
      }

      const ta = document.querySelector("textarea");
      const baseText = ta && ta.value.trim() ? ta.value.trim() + " " : "";

      recognition = new SpeechRecognition();
      recognition.lang = "gu-IN";
      recognition.interimResults = true;
      recognition.continuous = false;

      recognition.onstart = function () {
        isListening = true;
        micBtn.style.background = "#DC2626";
        micBtn.style.color = "#FFFFFF";
        micBtn.style.opacity = "1";
      };

      recognition.onresult = function (event) {
        let spoken = "";
        for (let i = 0; i < event.results.length; i++) {
          spoken += event.results[i][0].transcript;
        }
        const currentTa = document.querySelector("textarea");
        if (currentTa && spoken.trim()) {
          setReactTextareaValue(currentTa, baseText + spoken.trim());
          currentTa.focus();
        }
      };

      recognition.onerror = function () {
        isListening = false;
        micBtn.style.background = "transparent";
        micBtn.style.color = "inherit";
        micBtn.style.opacity = "0.85";
      };

      recognition.onend = function () {
        isListening = false;
        micBtn.style.background = "transparent";
        micBtn.style.color = "inherit";
        micBtn.style.opacity = "0.85";
      };

      try {
        recognition.start();
      } catch (err) {
        isListening = false;
      }
    });

    wrapper.appendChild(camBtn);
    wrapper.appendChild(micBtn);
    toolbarRow.appendChild(wrapper);
  }

  setInterval(injectInlineComposerIcons, 800);
})();
