(() => {
  function readErrorMessage(payload) {
    if (!payload) return "请求失败，请稍后重试。";
    if (typeof payload.detail === "string" && payload.detail) return payload.detail;
    if (typeof payload.message === "string" && payload.message) return payload.message;
    return "请求失败，请稍后重试。";
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(readErrorMessage(payload));
    }
    return payload;
  }

  async function getJson(url) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(readErrorMessage(payload));
    }
    return payload;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-ask-root]");
    if (!root) return;

    const suggestUrl = root.dataset.askSuggestUrl || "";
    const followupUrl = root.dataset.askFollowupUrl || "";
    const followupQuery = root.dataset.askFollowupQuery || "";
    const addUrl = root.dataset.watchlistAddUrl || "";
    const restoreUrl = root.dataset.watchlistRestoreUrl || "";

    const form = root.querySelector("[data-ask-search-form]");
    const input = root.querySelector("[data-ask-search-input]");
    const submitButton = root.querySelector("[data-ask-submit-button]");
    const submitButtonLabel = submitButton?.querySelector("span") || null;
    const submitDefaultLabel = submitButtonLabel?.textContent || "开始分析";
    const panel = root.querySelector("[data-ask-suggest-panel]");
    const status = root.querySelector("[data-ask-search-status]");
    const actionButton = root.querySelector("[data-ask-watchlist-action]");
    const actionFeedback = root.querySelector("[data-ask-watchlist-feedback]");
    const followupShell = root.querySelector("[data-ask-followup]");
    const followupForm = root.querySelector("[data-ask-followup-form]");
    const followupInput = root.querySelector("[data-ask-followup-input]");
    const followupStatus = root.querySelector("[data-ask-followup-status]");
    const followupThread = root.querySelector("[data-ask-followup-thread]");
    const followupPresetButtons = Array.from(root.querySelectorAll("[data-ask-followup-preset]"));

    let suggestionItems = [];
    let activeIndex = -1;
    let suggestTimer = 0;
    let suggestToken = 0;
    const followupHistory = [];
    const followupHistoryLimit = 6;

    function setSearchStatus(message, state = "info") {
      if (!status) return;
      status.textContent = message || "";
      if (message) {
        status.dataset.state = state;
      } else {
        delete status.dataset.state;
      }
    }

    function setSearchBusy(nextBusy) {
      if (!form || !submitButton) return;
      form.dataset.busy = nextBusy ? "true" : "false";
      submitButton.disabled = nextBusy;
      submitButton.classList.toggle("is-loading", nextBusy);
      if (submitButtonLabel) {
        submitButtonLabel.textContent = nextBusy ? "分析中..." : submitDefaultLabel;
      }
    }

    function setActionFeedback(message, state = "info") {
      if (!actionFeedback) return;
      actionFeedback.textContent = message || "";
      actionFeedback.dataset.state = state;
    }

    function setFollowupStatus(message, state = "info") {
      if (!followupStatus) return;
      followupStatus.textContent = message || "";
      followupStatus.dataset.state = state;
    }

    function hidePanel() {
      if (!panel) return;
      panel.innerHTML = "";
      panel.classList.add("hidden");
      suggestionItems = [];
      activeIndex = -1;
    }

    function updateActiveIndex(nextIndex) {
      if (!panel) return;
      const buttons = Array.from(panel.querySelectorAll(".ask-suggestion-item"));
      activeIndex = nextIndex;
      buttons.forEach((button, index) => {
        button.classList.toggle("is-active", index === activeIndex);
      });
    }

    function submitForm() {
      if (!form) return;
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
        return;
      }
      form.submit();
    }

    function selectSuggestion(index, submit = true) {
      const item = suggestionItems[index];
      if (!item || !input) return;
      input.value = item.fill_value || item.code || item.name || "";
      hidePanel();
      if (submit) {
        submitForm();
      } else {
        input.focus();
      }
    }

    function renderSuggestions(items) {
      if (!panel) return;
      panel.innerHTML = "";
      suggestionItems = items;
      activeIndex = -1;

      if (!items.length) {
        panel.classList.add("hidden");
        return;
      }

      items.forEach((item, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ask-suggestion-item";
        button.setAttribute("role", "option");
        button.dataset.index = String(index);

        const badge = document.createElement("span");
        badge.textContent = item.tag || "候选";
        const title = document.createElement("strong");
        title.textContent = item.name || item.code || "未命名";
        const detail = document.createElement("em");
        detail.textContent = item.detail || item.code || "";

        button.append(badge, title, detail);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
        });
        button.addEventListener("mouseenter", () => updateActiveIndex(index));
        button.addEventListener("click", () => selectSuggestion(index, true));
        panel.append(button);
      });

      panel.classList.remove("hidden");
    }

    function createFollowupMessage(role, payload = {}) {
      const article = document.createElement("article");
      article.className = `ask-followup-message ask-followup-message-${role}`;
      if (role === "assistant" && payload.tone) {
        article.classList.add(`tone-${payload.tone}`);
      }

      const badge = document.createElement("span");
      badge.textContent = role === "user" ? "你" : "棱镜";
      article.append(badge);

      const title = document.createElement("strong");
      title.textContent = payload.title || (role === "user" ? "继续追问" : "追问回答");
      article.append(title);

      if (role === "assistant" && payload.engineLabel) {
        const engine = document.createElement("em");
        engine.className = "ask-followup-engine";
        engine.textContent = payload.engineLabel;
        article.append(engine);
      }

      if (payload.summary) {
        const summary = document.createElement("p");
        summary.textContent = payload.summary;
        article.append(summary);
      }

      if (Array.isArray(payload.bullets) && payload.bullets.length) {
        const list = document.createElement("ul");
        list.className = "ask-followup-bullet-list";
        payload.bullets.forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          list.append(li);
        });
        article.append(list);
      }

      if (Array.isArray(payload.references) && payload.references.length) {
        const refs = document.createElement("ul");
        refs.className = "ask-followup-ref-strip";
        payload.references.forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          refs.append(li);
        });
        article.append(refs);
      }

      if (Array.isArray(payload.followups) && payload.followups.length) {
        const nextStrip = document.createElement("div");
        nextStrip.className = "ask-followup-preset-strip";
        payload.followups.forEach((item) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "ask-followup-preset";
          button.textContent = item;
          button.dataset.askFollowupQuestion = item;
          button.addEventListener("click", () => {
            if (followupInput) {
              followupInput.value = item;
            }
            submitFollowup(item);
          });
          nextStrip.append(button);
        });
        article.append(nextStrip);
      }

      return article;
    }

    function rememberFollowupHistory(role, payload = {}) {
      const entry = {
        role,
        title: payload.title || "",
        summary: payload.summary || "",
        bullets: Array.isArray(payload.bullets) ? payload.bullets.slice(0, 4) : [],
        references: Array.isArray(payload.references) ? payload.references.slice(0, 3) : [],
        engine_label: payload.engineLabel || "",
      };
      if (!entry.title && !entry.summary && !entry.bullets.length) return;
      followupHistory.push(entry);
      if (followupHistory.length > followupHistoryLimit) {
        followupHistory.splice(0, followupHistory.length - followupHistoryLimit);
      }
    }

    function appendFollowupMessage(role, payload) {
      if (!followupThread) return null;
      const message = createFollowupMessage(role, payload);
      followupThread.append(message);
      message.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return message;
    }

    function setFollowupBusy(nextBusy) {
      if (!followupShell) return;
      followupShell.setAttribute("aria-busy", nextBusy ? "true" : "false");
      if (followupInput) followupInput.disabled = nextBusy;
      followupPresetButtons.forEach((button) => {
        button.disabled = nextBusy;
      });
      const submitButton = followupForm?.querySelector("button[type='submit']");
      if (submitButton) submitButton.disabled = nextBusy;
    }

    async function submitFollowup(question) {
      const questionText = String(question || "").trim();
      if (!followupUrl || !followupQuery || !questionText) {
        setFollowupStatus("先输入一个具体问题。", "error");
        return;
      }

      setFollowupBusy(true);
      setFollowupStatus("正在整理这次追问...", "info");
      appendFollowupMessage("user", {
        title: "继续追问",
        summary: questionText,
      });

      const pending = appendFollowupMessage("assistant", {
        title: "正在整理回答",
        summary: "我会基于当前这次单票分析继续往下拆。",
        tone: "watch",
      });

      try {
        const payload = await postJson(followupUrl, {
          q: followupQuery,
          question: questionText,
          history: followupHistory.slice(-followupHistoryLimit),
        });
        if (pending) pending.remove();
        const answerPayload = {
          ...(payload.answer || {}),
          engineLabel: payload?.answer?.engine_label || "",
        };
        appendFollowupMessage("assistant", answerPayload);
        rememberFollowupHistory("user", {
          title: "继续追问",
          summary: questionText,
        });
        rememberFollowupHistory("assistant", answerPayload);
        setFollowupStatus(
          `已追加回答（${answerPayload.engineLabel || "规则托底"}），你可以继续追问下一个点。`,
          "success"
        );
        if (followupInput) {
          followupInput.value = "";
          followupInput.focus();
        }
      } catch (error) {
        if (pending) pending.remove();
        setFollowupStatus(error.message || "追问失败，请稍后重试。", "error");
      } finally {
        setFollowupBusy(false);
      }
    }

    async function loadSuggestions(query) {
      if (!suggestUrl || !panel) return;

      const currentToken = ++suggestToken;
      const url = query ? `${suggestUrl}?q=${encodeURIComponent(query)}` : suggestUrl;
      setSearchStatus(
        query ? "正在匹配系统内/历史库/全市场候选..." : "正在读取最近问过...",
        "loading"
      );

      try {
        const payload = await getJson(url);
        if (currentToken !== suggestToken) return;
        const items = Array.isArray(payload.items) ? payload.items : [];
        renderSuggestions(items);
        if (items.length) {
          setSearchStatus(payload.message || `找到 ${items.length} 个候选，可直接点卡片或按上下键选择。`, "success");
        } else if (query) {
          setSearchStatus(payload.message || "没找到直接候选，可按回车直接分析当前输入。", "watch");
        } else {
          setSearchStatus(payload.message || "", "info");
        }
      } catch (error) {
        if (currentToken !== suggestToken) return;
        hidePanel();
        setSearchStatus(error.message || "候选加载失败，请稍后再试。", "error");
      }
    }

    function scheduleSuggestions(query) {
      window.clearTimeout(suggestTimer);
      suggestTimer = window.setTimeout(() => {
        loadSuggestions(query);
      }, 160);
    }

    if (form && input) {
      form.addEventListener("submit", (event) => {
        const query = String(input.value || "").trim();
        if (!query) {
          event.preventDefault();
          setSearchStatus("先输入股票代码或名称。", "error");
          input.focus();
          return;
        }
        setSearchStatus("正在进入分析页...", "loading");
        setSearchBusy(true);
      });
    }

    if (input && panel) {
      input.addEventListener("focus", () => {
        setSearchBusy(false);
        scheduleSuggestions(String(input.value || "").trim());
      });

      input.addEventListener("input", () => {
        setSearchBusy(false);
        scheduleSuggestions(String(input.value || "").trim());
      });

      input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          hidePanel();
          return;
        }

        if (panel.classList.contains("hidden") || !suggestionItems.length) {
          if (event.key === "ArrowDown" && !panel.classList.contains("hidden")) {
            event.preventDefault();
          }
          return;
        }

        if (event.key === "ArrowDown") {
          event.preventDefault();
          updateActiveIndex(Math.min(activeIndex + 1, suggestionItems.length - 1));
          return;
        }

        if (event.key === "ArrowUp") {
          event.preventDefault();
          updateActiveIndex(Math.max(activeIndex - 1, 0));
          return;
        }

        if (event.key === "Enter" && activeIndex >= 0) {
          event.preventDefault();
          selectSuggestion(activeIndex, true);
        }
      });

      input.addEventListener("blur", () => {
        window.setTimeout(() => {
          hidePanel();
        }, 120);
      });

      document.addEventListener("click", (event) => {
        if (!root.contains(event.target)) {
          hidePanel();
        }
      });
    }

    if (actionButton) {
      actionButton.addEventListener("click", async () => {
        const action = actionButton.dataset.askWatchlistAction || "";
        const code = actionButton.dataset.watchlistCode || "";
        const name = actionButton.dataset.watchlistName || code;
        const url = action === "restore" ? restoreUrl : addUrl;
        const verb = action === "restore" ? "恢复" : "加入";
        if (!code || !url) return;

        actionButton.disabled = true;
        setActionFeedback(`${verb} ${name} 中...`, "info");

        try {
          const payload = await postJson(url, { code, name });
          setActionFeedback(payload.message || `${verb}完成。`, "success");
          actionButton.textContent = action === "restore" ? "已恢复，刷新中" : "已加入，刷新中";
          window.setTimeout(() => window.location.reload(), 450);
        } catch (error) {
          actionButton.disabled = false;
          setActionFeedback(error.message || `${verb}失败，请稍后重试。`, "error");
        }
      });
    }

    if (followupForm && followupInput) {
      followupForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitFollowup(followupInput.value);
      });
    }

    followupPresetButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const question = button.dataset.askFollowupQuestion || button.textContent || "";
        if (followupInput) {
          followupInput.value = question;
        }
        await submitFollowup(question);
      });
    });
  });
})();
